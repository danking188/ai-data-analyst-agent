from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session

from app.persistence.repositories import (
    AnalysisRunRepository,
    AnalysisSpecRepository,
    ArtifactRepository,
    AuditRepository,
    ClaimRepository,
    CleaningPlanRepository,
    ColumnSchemaRepository,
    DatasetRepository,
    IdempotencyRepository,
    JobRepository,
    ProjectRepository,
    QualityIssueRepository,
)


class UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.analysis_specs = AnalysisSpecRepository(session)
        self.runs = AnalysisRunRepository(session)
        self.datasets = DatasetRepository(session)
        self.jobs = JobRepository(session)
        self.schemas = ColumnSchemaRepository(session)
        self.quality_issues = QualityIssueRepository(session)
        self.idempotency = IdempotencyRepository(session)
        self.audit = AuditRepository(session)
        self.artifacts = ArtifactRepository(session)
        self.claims = ClaimRepository(session)
        self.cleaning_plans = CleaningPlanRepository(session)

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del traceback
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
