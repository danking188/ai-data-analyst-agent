from __future__ import annotations

import html
import json
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.core.ids import new_id
from app.domain.errors import DomainError
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import ArtifactRow, ClaimRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage


class ReportExportWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        *,
        worker_id: str,
    ) -> None:
        self.database = database
        self.storage = storage
        self.worker_id = worker_id

    def run(self, job_id: str) -> bool:
        if not self._claim(job_id):
            return False
        try:
            self._process(job_id)
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
            notebook = self._notebook(manifest, claims, request)
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
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>AI Data Analyst "
            "Report</title></head><body>"
            f"<h1>分析报告</h1><p>Run: {html.escape(manifest['run_id'])}</p>"
            f"<h2>结论</h2><ol>{claim_items}</ol>"
            f"<h2>证据 Artifact</h2><ul>{artifact_items}</ul>"
            f"<h2>Manifest</h2><pre>{manifest_json}</pre>"
            "</body></html>"
        )

    @staticmethod
    def _notebook(
        manifest: dict[str, Any],
        claims: list[ClaimRow],
        request: dict[str, Any],
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
    from app.core.config import get_settings

    ReportExportWorker(
        get_database(),
        FileStorage(get_settings().data_root),
        worker_id=f"local:{job_id}",
    ).run(job_id)
