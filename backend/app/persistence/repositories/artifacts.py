from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found
from app.persistence.orm.workflow_models import ArtifactRow
from app.persistence.repositories.projects import Page


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_cleaning_preview(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        plan_id: str,
        result: dict[str, Any],
    ) -> ArtifactRow:
        canonical = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        row = ArtifactRow(
            artifact_id=new_id("art_"),
            project_id=project_id,
            run_id=None,
            dataset_version_id=dataset_version_id,
            type="comparison",
            name="清洗影响预览",
            producer="cleaning_preview",
            producer_version="1.0.0",
            status="ready",
            parameters_json={"cleaning_plan_id": plan_id},
            result_json=result,
            preview_json=result,
            storage_key=None,
            checksum=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            downloadable=False,
            created_at=utc_now(),
            ready_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_version_comparison(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        base_version_id: str,
        result: dict[str, Any],
    ) -> ArtifactRow:
        canonical = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        row = ArtifactRow(
            artifact_id=new_id("art_"),
            project_id=project_id,
            run_id=None,
            dataset_version_id=dataset_version_id,
            type="comparison",
            name="数据版本比较",
            producer="version_comparison",
            producer_version="1.0.0",
            status="ready",
            parameters_json={
                "base_version_id": base_version_id,
                "compare_version_id": dataset_version_id,
            },
            result_json=result,
            preview_json=result,
            storage_key=None,
            checksum=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            downloadable=False,
            created_at=utc_now(),
            ready_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_assistant_artifact(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        name: str,
        producer: str,
        result: dict[str, Any],
    ) -> ArtifactRow:
        canonical = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        row = ArtifactRow(
            artifact_id=new_id("art_"),
            project_id=project_id,
            run_id=None,
            dataset_version_id=dataset_version_id,
            type="log",
            name=name,
            producer=producer,
            producer_version="1.0.0",
            status="ready",
            parameters_json={"source": "assistant"},
            result_json=result,
            preview_json=result,
            storage_key=None,
            checksum=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            downloadable=False,
            created_at=utc_now(),
            ready_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_analysis_artifact(
        self,
        *,
        project_id: str,
        run_id: str,
        dataset_version_id: str,
        artifact_type: str,
        name: str,
        producer: str,
        producer_version: str,
        parameters: dict[str, Any],
        result: Any,
        preview: Any | None = None,
        downloadable: bool = False,
        storage_key: str | None = None,
    ) -> ArtifactRow:
        canonical = json.dumps(
            {
                "parameters": parameters,
                "result": result,
                "preview": preview,
                "storage_key": storage_key,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        row = ArtifactRow(
            artifact_id=new_id("art_"),
            project_id=project_id,
            run_id=run_id,
            dataset_version_id=dataset_version_id,
            type=artifact_type,
            name=name,
            producer=producer,
            producer_version=producer_version,
            status="ready",
            parameters_json=parameters,
            result_json=result,
            preview_json=preview if preview is not None else result,
            storage_key=storage_key,
            checksum=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            downloadable=downloadable,
            created_at=utc_now(),
            ready_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def create_file_export(
        self,
        *,
        artifact_id: str,
        project_id: str,
        run_id: str,
        dataset_version_id: str,
        name: str,
        producer: str,
        producer_version: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
        preview: dict[str, Any],
        storage_key: str,
        checksum: str,
    ) -> ArtifactRow:
        row = ArtifactRow(
            artifact_id=artifact_id,
            project_id=project_id,
            run_id=run_id,
            dataset_version_id=dataset_version_id,
            type="file",
            name=name,
            producer=producer,
            producer_version=producer_version,
            status="ready",
            parameters_json=parameters,
            result_json=result,
            preview_json=preview,
            storage_key=storage_key,
            checksum=checksum,
            downloadable=True,
            created_at=utc_now(),
            ready_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, *, project_id: str, artifact_id: str) -> ArtifactRow:
        row = self.session.scalar(
            select(ArtifactRow).where(
                ArtifactRow.project_id == project_id,
                ArtifactRow.artifact_id == artifact_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def list_for_run(
        self,
        *,
        project_id: str,
        run_id: str,
        page: int,
        page_size: int,
        artifact_type: str | None,
    ) -> Page[ArtifactRow]:
        filters = [
            ArtifactRow.project_id == project_id,
            ArtifactRow.run_id == run_id,
        ]
        if artifact_type is not None:
            filters.append(ArtifactRow.type == artifact_type)
        total = int(
            self.session.scalar(select(func.count()).select_from(ArtifactRow).where(*filters)) or 0
        )
        rows = list(
            self.session.scalars(
                select(ArtifactRow)
                .where(*filters)
                .order_by(ArtifactRow.created_at.asc(), ArtifactRow.artifact_id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, total=total, page=page, page_size=page_size)
