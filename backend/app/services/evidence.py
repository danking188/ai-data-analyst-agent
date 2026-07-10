from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.api.schemas import Artifact, ArtifactPage, Claim, ClaimPage, Download
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.workflow_models import ArtifactRow, ClaimRow
from app.persistence.repositories.artifacts import ArtifactRepository
from app.persistence.repositories.claims import ClaimRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.runs import AnalysisRunRepository


class EvidenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.runs = AnalysisRunRepository(session)
        self.artifacts = ArtifactRepository(session)
        self.claims = ClaimRepository(session)

    def require_project_access(self, project_id: str, subject_id: str) -> None:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        _, role = membership
        if role not in {"owner", "editor", "viewer"}:
            raise permission_denied()

    def artifact_to_schema(self, row: ArtifactRow) -> Artifact:
        return Artifact(
            artifact_id=row.artifact_id,
            project_id=row.project_id,
            run_id=row.run_id,
            dataset_version_id=row.dataset_version_id,
            type=row.type,
            name=row.name,
            producer=row.producer,
            producer_version=row.producer_version,
            status=row.status,
            parameters=row.parameters_json,
            result=row.result_json,
            preview=row.preview_json,
            checksum=row.checksum,
            downloadable=row.downloadable,
            created_at=row.created_at,
        )

    def list_artifacts(
        self,
        project_id: str,
        run_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        artifact_type: str | None,
    ) -> ArtifactPage:
        self.require_project_access(project_id, subject_id)
        self.runs.get(project_id=project_id, run_id=run_id)
        result = self.artifacts.list_for_run(
            project_id=project_id,
            run_id=run_id,
            page=page,
            page_size=page_size,
            artifact_type=artifact_type,
        )
        return ArtifactPage(
            items=[self.artifact_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get_artifact(
        self,
        project_id: str,
        artifact_id: str,
        *,
        subject_id: str,
    ) -> Artifact:
        self.require_project_access(project_id, subject_id)
        row = self.artifacts.get(project_id=project_id, artifact_id=artifact_id)
        return self.artifact_to_schema(row)

    def claim_to_schema(self, row: ClaimRow) -> Claim:
        return Claim(
            claim_id=row.claim_id,
            project_id=row.project_id,
            run_id=row.run_id,
            dataset_version_id=row.dataset_version_id,
            text=row.text,
            level=row.level,
            evidence_ids=self.claims.evidence_ids(row.claim_id),
            limitations=row.limitations_json,
            validation_status=row.validation_status,
            validation_messages=row.validation_messages_json,
            publication_status=row.publication_status,
            created_at=row.created_at,
        )

    def list_claims(
        self,
        project_id: str,
        run_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        validation_status: str | None,
    ) -> ClaimPage:
        self.require_project_access(project_id, subject_id)
        self.runs.get(project_id=project_id, run_id=run_id)
        result = self.claims.list_for_run(
            project_id=project_id,
            run_id=run_id,
            page=page,
            page_size=page_size,
            validation_status=validation_status,
        )
        return ClaimPage(
            items=[self.claim_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get_claim(
        self,
        project_id: str,
        claim_id: str,
        *,
        subject_id: str,
    ) -> Claim:
        self.require_project_access(project_id, subject_id)
        row = self.claims.get(project_id=project_id, claim_id=claim_id)
        return self.claim_to_schema(row)

    def create_download(
        self,
        project_id: str,
        artifact_id: str,
        *,
        subject_id: str,
        download_url: str,
        expires_at: datetime,
    ) -> Download:
        artifact = self.get_downloadable_artifact(
            project_id,
            artifact_id,
            subject_id=subject_id,
        )
        result = artifact.result_json if isinstance(artifact.result_json, dict) else {}
        file_name = str(result.get("file_name") or f"{artifact.artifact_id}.artifact")
        return Download(
            download_url=download_url,
            file_name=file_name,
            content_type=result.get("content_type"),
            size_bytes=result.get("size_bytes"),
            expires_at=expires_at,
        )

    def get_downloadable_artifact(
        self,
        project_id: str,
        artifact_id: str,
        *,
        subject_id: str,
    ) -> ArtifactRow:
        self.require_project_access(project_id, subject_id)
        artifact = self.artifacts.get(project_id=project_id, artifact_id=artifact_id)
        if not artifact.downloadable or not artifact.storage_key:
            raise state_conflict("该 Artifact 不支持下载")
        return artifact
