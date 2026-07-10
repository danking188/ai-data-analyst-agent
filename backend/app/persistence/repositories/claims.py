from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found
from app.persistence.orm.workflow_models import (
    ClaimEvidenceRow,
    ClaimRow,
    ValidationResultRow,
)
from app.persistence.repositories.projects import Page

NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?%?")


class ClaimRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_validated(
        self,
        *,
        project_id: str,
        run_id: str,
        dataset_version_id: str,
        text: str,
        level: int,
        evidence_ids: list[str],
        limitations: list[str],
    ) -> ClaimRow:
        messages = self.validate_claim_text(text, evidence_ids)
        status = "passed" if not messages else "failed"
        now = utc_now()
        claim = ClaimRow(
            claim_id=new_id("claim_"),
            project_id=project_id,
            run_id=run_id,
            dataset_version_id=dataset_version_id,
            text=text,
            level=level,
            limitations_json=limitations,
            validation_status=status,
            validation_messages_json=messages,
            publication_status="draft",
            created_at=now,
            updated_at=now,
        )
        self.session.add(claim)
        self.session.flush()
        for position, artifact_id in enumerate(evidence_ids, start=1):
            self.session.add(
                ClaimEvidenceRow(
                    claim_id=claim.claim_id,
                    artifact_id=artifact_id,
                    position=position,
                )
            )
        self.session.add(
            ValidationResultRow(
                validation_id=new_id("val_"),
                project_id=project_id,
                claim_id=claim.claim_id,
                validator="claim.numeric_evidence",
                validator_version="1.0.0",
                status=status,
                details_json={
                    "numeric_tokens": NUMBER_PATTERN.findall(text),
                    "evidence_ids": evidence_ids,
                    "messages": messages,
                },
                created_at=now,
            )
        )
        self.session.flush()
        return claim

    @staticmethod
    def validate_claim_text(text: str, evidence_ids: list[str]) -> list[str]:
        has_numeric_claim = bool(NUMBER_PATTERN.search(text))
        if has_numeric_claim and not evidence_ids:
            return ["结论包含数字，但没有绑定任何证据 Artifact"]
        return []

    def evidence_ids(self, claim_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(ClaimEvidenceRow.artifact_id)
                .where(ClaimEvidenceRow.claim_id == claim_id)
                .order_by(ClaimEvidenceRow.position)
            )
        )

    def get(self, *, project_id: str, claim_id: str) -> ClaimRow:
        row = self.session.scalar(
            select(ClaimRow).where(
                ClaimRow.project_id == project_id,
                ClaimRow.claim_id == claim_id,
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
        validation_status: str | None,
    ) -> Page[ClaimRow]:
        filters = [
            ClaimRow.project_id == project_id,
            ClaimRow.run_id == run_id,
        ]
        if validation_status is not None:
            filters.append(ClaimRow.validation_status == validation_status)
        total = int(
            self.session.scalar(select(func.count()).select_from(ClaimRow).where(*filters)) or 0
        )
        rows = list(
            self.session.scalars(
                select(ClaimRow)
                .where(*filters)
                .order_by(ClaimRow.created_at.asc(), ClaimRow.claim_id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, total=total, page=page, page_size=page_size)
