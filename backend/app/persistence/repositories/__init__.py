"""SQLAlchemy repositories used by application services."""

from app.persistence.repositories.analysis_specs import AnalysisSpecRepository
from app.persistence.repositories.artifacts import ArtifactRepository
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.claims import ClaimRepository
from app.persistence.repositories.cleaning import CleaningPlanRepository
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.idempotency import (
    IdempotencyRecord,
    IdempotencyRepository,
    canonical_request_hash,
)
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.projects import Page, ProjectRepository
from app.persistence.repositories.quality import QualityIssueRepository
from app.persistence.repositories.runs import AnalysisRunRepository
from app.persistence.repositories.schemas import ColumnSchemaRepository
from app.persistence.repositories.users import UserRepository

__all__ = [
    "AnalysisSpecRepository",
    "AnalysisRunRepository",
    "AuditRepository",
    "ArtifactRepository",
    "CleaningPlanRepository",
    "ClaimRepository",
    "ColumnSchemaRepository",
    "DatasetRepository",
    "DatasetVersionDraft",
    "IdempotencyRecord",
    "IdempotencyRepository",
    "JobRepository",
    "Page",
    "ProjectRepository",
    "QualityIssueRepository",
    "UserRepository",
    "canonical_request_hash",
]
