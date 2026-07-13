from __future__ import annotations

import html
import json
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.core.config import get_settings
from app.core.ids import new_id
from app.domain.errors import DomainError
from app.llm.citations import CitationValidationError
from app.llm.context import EvidenceContext, build_evidence_context
from app.llm.factory import get_llm_provider
from app.llm.narrative import PROMPT_NAME, PROMPT_VERSION, generate_evidence_narrative
from app.llm.provider import LLMProvider, LLMProviderError
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import (
    AnalysisSpecRow,
    ArtifactRow,
    ClaimEvidenceRow,
    ClaimRow,
)
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.runs import AnalysisRunRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage, get_file_storage


class ReportExportWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        *,
        worker_id: str,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.database = database
        self.storage = storage
        self.worker_id = worker_id
        self.llm_provider = llm_provider

    def run(self, job_id: str) -> bool:
        if not self._claim(job_id):
            return False
        try:
            self._process(job_id)
        except LLMProviderError as exc:
            self._fail(
                job_id,
                DomainError(exc.code, exc.message, 503, retryable=exc.retryable),
            )
        except CitationValidationError:
            self._fail(
                job_id,
                DomainError(
                    "LLM_EVIDENCE_VALIDATION_FAILED",
                    "大模型解读未通过证据一致性校验",
                    422,
                ),
            )
        except DomainError as exc:
            self._fail(job_id, exc)
        except Exception:
            self._fail(
                job_id,
                DomainError("REPORT_EXPORT_FAILED", "报告导出失败", 500, retryable=True),
            )
        return True

    def _claim(self, job_id: str) -> bool:
        session = self.database.session()
        try:
            with UnitOfWork(session):
                return JobRepository(session).claim(
                    job_id=job_id,
                    worker_id=self.worker_id,
                    lease_seconds=1800,
                )
        finally:
            session.close()

    def _process(self, job_id: str) -> None:
        request = self._load_job_request(job_id)
        if request.get("format") == "ai_narrative":
            self._process_ai_narrative(job_id, request)
            return
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.kind != "report_export":
                    raise DomainError("STATE_CONFLICT", "Job 类型不是报告导出", 409)
                request = dict(job.request_json)
                run = uow.runs.get(
                    project_id=job.project_id,
                    run_id=str(request["run_id"]),
                )
                version = session.get(DatasetVersionRow, run.dataset_version_id)
                if version is None or not version.data_storage_key:
                    raise DomainError("STATE_CONFLICT", "运行数据版本尚未就绪", 409)
                claims = list(
                    session.scalars(
                        select(ClaimRow)
                        .where(
                            ClaimRow.project_id == job.project_id,
                            ClaimRow.run_id == run.run_id,
                            ClaimRow.claim_id.in_(list(request.get("claim_ids", []))),
                        )
                        .order_by(ClaimRow.created_at.asc())
                    )
                )
                artifacts = list(
                    session.scalars(
                        select(ArtifactRow)
                        .where(
                            ArtifactRow.project_id == job.project_id,
                            ArtifactRow.run_id == run.run_id,
                            ArtifactRow.status == "ready",
                        )
                        .order_by(ArtifactRow.created_at.asc())
                    )
                )
                payload = self._render(
                    request=request,
                    project_id=job.project_id,
                    run_id=run.run_id,
                    dataset_version_id=run.dataset_version_id,
                    data_storage_key=version.data_storage_key,
                    claims=claims,
                    artifacts=artifacts,
                )
                artifact_id = new_id("art_")
                storage_key = self.storage.write_artifact_file(
                    project_id=job.project_id,
                    artifact_id=artifact_id,
                    file_name=payload["file_name"],
                    content=payload["content"],
                )
                checksum = self.storage.checksum_path(self.storage.resolve_key(storage_key))
                artifact = uow.artifacts.create_file_export(
                    artifact_id=artifact_id,
                    project_id=job.project_id,
                    run_id=run.run_id,
                    dataset_version_id=run.dataset_version_id,
                    name=payload["name"],
                    producer="report_export",
                    producer_version="1.0.0",
                    parameters={
                        "format": request["format"],
                        "claim_ids": request.get("claim_ids", []),
                        "include_code": request.get("include_code", True),
                        "include_evidence": request.get("include_evidence", True),
                        "data_format": request.get("data_format"),
                    },
                    result={
                        "file_name": payload["file_name"],
                        "content_type": payload["content_type"],
                        "size_bytes": len(payload["content"]),
                    },
                    preview=payload["preview"],
                    storage_key=storage_key,
                    checksum=checksum,
                )
                uow.jobs.transition(
                    job,
                    status="succeeded",
                    resource_type="artifact",
                    resource_id=artifact.artifact_id,
                )
                uow.audit.append(
                    action="report_export.completed",
                    result="success",
                    summary={"format": request["format"], "artifact_id": artifact.artifact_id},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="artifact",
                    object_id=artifact.artifact_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            session.close()

    def _load_job_request(self, job_id: str) -> dict[str, Any]:
        session = self.database.session()
        try:
            job = JobRepository(session).get(job_id)
            if job.kind != "report_export":
                raise DomainError("STATE_CONFLICT", "Job 类型不是报告导出", 409)
            return dict(job.request_json)
        finally:
            session.close()

    def _process_ai_narrative(self, job_id: str, request: dict[str, Any]) -> None:
        settings = get_settings()
        provider = self.llm_provider or get_llm_provider()
        if provider is None or not settings.llm_model:
            raise DomainError("LLM_DISABLED", "当前部署尚未启用大模型证据解读", 409)
        context = self._load_evidence_context(
            job_id,
            request,
            max_chars=max(settings.llm_max_input_tokens * 4 - 4000, 1000),
        )
        response = generate_evidence_narrative(
            provider=provider,
            context=context,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.status not in {"running", "cancelling"}:
                    raise DomainError("STATE_CONFLICT", "报告任务不在可完成状态", 409)
                artifact = uow.artifacts.create_analysis_artifact(
                    project_id=context.project_id,
                    run_id=context.run_id,
                    dataset_version_id=context.dataset_version_id,
                    artifact_type="log",
                    name="AI 证据解读",
                    producer="llm_report_narrative",
                    producer_version=PROMPT_VERSION,
                    parameters={
                        "provider": response.provider,
                        "model": response.model,
                        "prompt_name": PROMPT_NAME,
                        "prompt_version": PROMPT_VERSION,
                        "provider_request_id": response.request_id,
                        "context_manifest": context.manifest(),
                        "usage": response.usage.model_dump(),
                        "latency_ms": response.latency_ms,
                    },
                    result=response.content.model_dump(mode="json"),
                    preview=response.content.model_dump(mode="json"),
                )
                uow.jobs.transition(
                    job,
                    status="succeeded",
                    resource_type="artifact",
                    resource_id=artifact.artifact_id,
                )
                uow.audit.append(
                    action="llm_report_narrative.completed",
                    result="success",
                    summary={
                        "artifact_id": artifact.artifact_id,
                        "provider": response.provider,
                        "model": response.model,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                    project_id=context.project_id,
                    subject_id=job.created_by,
                    object_type="artifact",
                    object_id=artifact.artifact_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            session.close()

    def _load_evidence_context(
        self,
        job_id: str,
        request: dict[str, Any],
        *,
        max_chars: int,
    ) -> EvidenceContext:
        session = self.database.session()
        try:
            job = JobRepository(session).get(job_id)
            analysis_run = AnalysisRunRepository(session).get(
                project_id=job.project_id,
                run_id=str(request["run_id"]),
            )
            spec = session.get(AnalysisSpecRow, analysis_run.analysis_spec_revision_id)
            if spec is None:
                raise DomainError("STATE_CONFLICT", "分析定义不存在", 409)
            claim_ids = list(request.get("claim_ids", []))
            claims = list(
                session.scalars(
                    select(ClaimRow)
                    .where(
                        ClaimRow.project_id == job.project_id,
                        ClaimRow.run_id == analysis_run.run_id,
                        ClaimRow.validation_status == "passed",
                        ClaimRow.claim_id.in_(claim_ids),
                    )
                    .order_by(ClaimRow.created_at.asc())
                )
            )
            evidence_rows = list(
                session.execute(
                    select(ClaimEvidenceRow.claim_id, ClaimEvidenceRow.artifact_id)
                    .where(ClaimEvidenceRow.claim_id.in_([claim.claim_id for claim in claims]))
                    .order_by(ClaimEvidenceRow.claim_id, ClaimEvidenceRow.position)
                )
            )
            evidence_by_claim: dict[str, list[str]] = {}
            for claim_id, artifact_id in evidence_rows:
                evidence_by_claim.setdefault(str(claim_id), []).append(str(artifact_id))
            artifact_ids = sorted({str(artifact_id) for _, artifact_id in evidence_rows})
            artifacts = list(
                session.scalars(
                    select(ArtifactRow)
                    .where(
                        ArtifactRow.project_id == job.project_id,
                        ArtifactRow.run_id == analysis_run.run_id,
                        ArtifactRow.dataset_version_id == analysis_run.dataset_version_id,
                        ArtifactRow.status == "ready",
                        ArtifactRow.artifact_id.in_(artifact_ids),
                    )
                    .order_by(ArtifactRow.created_at.asc())
                )
            )
            return build_evidence_context(
                project_id=job.project_id,
                run_id=analysis_run.run_id,
                dataset_version_id=analysis_run.dataset_version_id,
                causal_interpretation_allowed=spec.causal_interpretation_allowed,
                claims=[
                    {
                        "claim_id": claim.claim_id,
                        "text": claim.text,
                        "level": claim.level,
                        "evidence_ids": evidence_by_claim.get(claim.claim_id, []),
                        "limitations": list(claim.limitations_json),
                    }
                    for claim in claims
                ],
                artifacts=[
                    {
                        "artifact_id": artifact.artifact_id,
                        "artifact_type": artifact.type,
                        "name": artifact.name,
                        "producer": artifact.producer,
                        "producer_version": artifact.producer_version,
                        "checksum": artifact.checksum,
                        "result": artifact.result_json,
                    }
                    for artifact in artifacts
                ],
                max_chars=max_chars,
            )
        finally:
            session.close()

    def _render(
        self,
        *,
        request: dict[str, Any],
        project_id: str,
        run_id: str,
        dataset_version_id: str,
        data_storage_key: str,
        claims: list[ClaimRow],
        artifacts: list[ArtifactRow],
    ) -> dict[str, Any]:
        export_format = str(request["format"])
        if export_format == "cleaned_data":
            data_format = str(request["data_format"])
            frame = pd.read_parquet(self.storage.resolve_key(data_storage_key))
            if data_format == "csv":
                content = frame.to_csv(index=False).encode("utf-8")
                return self._payload(
                    name="清洗后数据 CSV 导出",
                    file_name=f"{dataset_version_id}.csv",
                    content_type="text/csv",
                    content=content,
                    preview={"rows": len(frame), "columns": len(frame.columns)},
                )
            parquet_bytes = self.storage.resolve_key(data_storage_key).read_bytes()
            return self._payload(
                name="清洗后数据 Parquet 导出",
                file_name=f"{dataset_version_id}.parquet",
                content_type="application/vnd.apache.parquet",
                content=parquet_bytes,
                preview={"rows": len(frame), "columns": len(frame.columns)},
            )
        manifest = {
            "project_id": project_id,
            "run_id": run_id,
            "dataset_version_id": dataset_version_id,
            "claim_ids": [claim.claim_id for claim in claims],
            "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            "artifact_checksums": {
                artifact.artifact_id: artifact.checksum for artifact in artifacts
            },
            "llm_narratives": [
                {
                    "artifact_id": artifact.artifact_id,
                    "provider": artifact.parameters_json.get("provider"),
                    "model": artifact.parameters_json.get("model"),
                    "prompt_name": artifact.parameters_json.get("prompt_name"),
                    "prompt_version": artifact.parameters_json.get("prompt_version"),
                }
                for artifact in artifacts
                if artifact.producer == "llm_report_narrative"
            ],
        }
        if export_format == "manifest":
            content = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            return self._payload(
                name="可重跑 Manifest",
                file_name=f"{run_id}-manifest.json",
                content_type="application/json",
                content=content,
                preview=manifest,
            )
        if export_format == "notebook":
            notebook = self._notebook(
                manifest,
                claims,
                request,
                self._latest_narrative(artifacts),
            )
            content = json.dumps(notebook, ensure_ascii=False, indent=2).encode("utf-8")
            return self._payload(
                name="分析 Notebook 导出",
                file_name=f"{run_id}.ipynb",
                content_type="application/x-ipynb+json",
                content=content,
                preview={"cell_count": len(notebook["cells"]), "claim_count": len(claims)},
            )
        content = self._html(manifest, claims, artifacts, request).encode("utf-8")
        return self._payload(
            name="HTML 报告导出",
            file_name=f"{run_id}.html",
            content_type="text/html; charset=utf-8",
            content=content,
            preview={"claim_count": len(claims), "artifact_count": len(artifacts)},
        )

    @staticmethod
    def _payload(
        *,
        name: str,
        file_name: str,
        content_type: str,
        content: bytes,
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "file_name": file_name,
            "content_type": content_type,
            "content": content,
            "preview": preview,
        }

    @staticmethod
    def _html(
        manifest: dict[str, Any],
        claims: list[ClaimRow],
        artifacts: list[ArtifactRow],
        request: dict[str, Any],
    ) -> str:
        claim_items = "\n".join(
            f"<li>{html.escape(claim.text)}<br><small>证据："
            f"{', '.join(html.escape(item) for item in request.get('claim_ids', []))}</small></li>"
            for claim in claims
        )
        artifact_items = "\n".join(
            f"<li>{html.escape(artifact.name)} — {html.escape(artifact.type)} — "
            f"{html.escape(artifact.checksum)}</li>"
            for artifact in artifacts
        )
        manifest_json = html.escape(json.dumps(manifest, ensure_ascii=False, indent=2))
        narrative = ReportExportWorker._latest_narrative(artifacts)
        narrative_html = ""
        if narrative:
            findings = narrative.get("findings", [])
            finding_items = "".join(
                "<li>"
                + html.escape(str(item.get("text", "")))
                + "<br><small>引用："
                + html.escape(", ".join(str(value) for value in item.get("citation_ids", [])))
                + "</small></li>"
                for item in findings
                if isinstance(item, dict)
            )
            narrative_html = (
                "<h2>AI 证据解读</h2>"
                f"<p>{html.escape(str(narrative.get('summary', '')))}</p>"
                f"<ol>{finding_items}</ol>"
            )
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>AI Data Analyst "
            "Report</title></head><body>"
            f"<h1>分析报告</h1><p>Run: {html.escape(manifest['run_id'])}</p>"
            f"<h2>结论</h2><ol>{claim_items}</ol>"
            f"{narrative_html}"
            f"<h2>证据 Artifact</h2><ul>{artifact_items}</ul>"
            f"<h2>Manifest</h2><pre>{manifest_json}</pre>"
            "</body></html>"
        )

    @staticmethod
    def _notebook(
        manifest: dict[str, Any],
        claims: list[ClaimRow],
        request: dict[str, Any],
        narrative: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cells: list[dict[str, Any]] = [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# AI Data Analyst Agent 导出\n", f"Run: `{manifest['run_id']}`\n"],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## 结论\n",
                    *[f"- {claim.text}\n" for claim in claims],
                ],
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Manifest\n",
                    "```json\n",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    "\n```\n",
                ],
            },
        ]
        if narrative:
            cells.insert(
                2,
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        "## AI 证据解读\n",
                        f"{narrative.get('summary', '')}\n",
                        *[
                            f"- {item.get('text', '')}"
                            f"（引用：{', '.join(item.get('citation_ids', []))}）\n"
                            for item in narrative.get("findings", [])
                            if isinstance(item, dict)
                        ],
                    ],
                },
            )
        if request.get("include_code", True):
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Re-run this analysis through the public API.\n",
                        "import json\n",
                        "import os\n",
                        "import uuid\n",
                        "import urllib.request\n",
                        "from http.cookiejar import CookieJar\n",
                        "\n",
                        "API_BASE_URL = os.getenv('DATATRACE_API_URL', 'http://localhost:8000/api/v1').rstrip('/')\n",
                        "LOGIN_USERNAME = os.getenv('DATATRACE_USERNAME')\n",
                        "LOGIN_PASSWORD = os.getenv('DATATRACE_PASSWORD')\n",
                        "API_TOKEN = os.getenv('DATATRACE_API_TOKEN')\n",
                        f"PROJECT_ID = {manifest['project_id']!r}\n",
                        f"RUN_ID = {manifest['run_id']!r}\n",
                        f"DATASET_VERSION_ID = {manifest['dataset_version_id']!r}\n",
                        "\n",
                        "opener = urllib.request.build_opener(\n",
                        "    urllib.request.HTTPCookieProcessor(CookieJar())\n",
                        ")\n",
                        "\n",
                        "def api_request(path, *, method='GET', body=None, extra_headers=None):\n",
                        "    headers = {\n",
                        "        'Content-Type': 'application/json',\n",
                        "        **(extra_headers or {}),\n",
                        "    }\n",
                        "    if API_TOKEN:\n",
                        "        headers['Authorization'] = f'Bearer {API_TOKEN}'\n",
                        "    payload = json.dumps(body).encode() if body is not None else None\n",
                        "    request = urllib.request.Request(\n",
                        "        f'{API_BASE_URL}{path}',\n",
                        "        data=payload,\n",
                        "        headers=headers,\n",
                        "        method=method,\n",
                        "    )\n",
                        "    with opener.open(request) as response:\n",
                        "        content = response.read()\n",
                        "        return json.loads(content) if content else None\n",
                        "\n",
                        "if LOGIN_USERNAME and LOGIN_PASSWORD and not API_TOKEN:\n",
                        "    api_request(\n",
                        "        '/auth/login',\n",
                        "        method='POST',\n",
                        "        body={'username': LOGIN_USERNAME, 'password': LOGIN_PASSWORD},\n",
                        "    )\n",
                        "\n",
                        "source_run = api_request(f'/projects/{PROJECT_ID}/runs/{RUN_ID}')\n",
                        "rerun = api_request(\n",
                        "    f'/projects/{PROJECT_ID}/runs',\n",
                        "    method='POST',\n",
                        "    body={\n",
                        "        'analysis_spec_id': source_run['analysis_spec_id'],\n",
                        "        'dataset_version_id': DATASET_VERSION_ID,\n",
                        "        'run_kind': source_run['run_kind'],\n",
                        "    },\n",
                        "    extra_headers={\n",
                        "        'Idempotency-Key': f'notebook-rerun-{uuid.uuid4()}',\n",
                        "    },\n",
                        ")\n",
                        "rerun\n",
                    ],
                }
            )
        return {
            "cells": cells,
            "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    @staticmethod
    def _latest_narrative(artifacts: list[ArtifactRow]) -> dict[str, Any] | None:
        narratives = [
            artifact.result_json
            for artifact in artifacts
            if artifact.producer == "llm_report_narrative"
            and isinstance(artifact.result_json, dict)
        ]
        return dict(narratives[-1]) if narratives else None

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                payload = {
                    "code": error.code,
                    "message": error.message,
                    "request_id": f"job:{job_id}",
                    "retryable": error.retryable,
                    "details": error.details,
                }
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(job, status="failed", error=payload)
                uow.audit.append(
                    action="report_export.failed",
                    result="failed",
                    summary={"retryable": error.retryable},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="job",
                    object_id=job_id,
                    request_id=f"job:{job_id}",
                    error_code=error.code,
                )
        finally:
            session.close()


def process_report_export_job(job_id: str) -> None:
    ReportExportWorker(
        get_database(),
        get_file_storage(),
        worker_id=f"local:{job_id}",
    ).run(job_id)
