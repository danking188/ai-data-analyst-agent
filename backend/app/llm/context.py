from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    artifact_type: str
    name: str
    producer: str
    producer_version: str
    checksum: str
    result: Any


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    text: str
    level: int = Field(ge=1, le=5)
    evidence_ids: list[str]
    limitations: list[str]


class EvidenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    run_id: str
    dataset_version_id: str
    causal_interpretation_allowed: bool
    claims: list[EvidenceClaim]
    artifacts: list[EvidenceArtifact]

    def manifest(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "dataset_version_id": self.dataset_version_id,
            "claim_ids": [claim.claim_id for claim in self.claims],
            "artifact_ids": [artifact.artifact_id for artifact in self.artifacts],
            "artifact_checksums": {
                artifact.artifact_id: artifact.checksum for artifact in self.artifacts
            },
        }

    def prompt_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def build_evidence_context(
    *,
    project_id: str,
    run_id: str,
    dataset_version_id: str,
    causal_interpretation_allowed: bool,
    claims: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    max_chars: int,
) -> EvidenceContext:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    context = EvidenceContext(
        project_id=project_id,
        run_id=run_id,
        dataset_version_id=dataset_version_id,
        causal_interpretation_allowed=causal_interpretation_allowed,
        claims=[EvidenceClaim.model_validate(item) for item in claims],
        artifacts=[
            EvidenceArtifact.model_validate({**item, "result": _summarize(item.get("result"))})
            for item in artifacts
        ],
    )
    if len(context.prompt_json()) <= max_chars:
        return context

    compact_artifacts = [
        artifact.model_copy(update={"result": {"omitted": "context_budget"}})
        for artifact in context.artifacts
    ]
    compact = context.model_copy(update={"artifacts": compact_artifacts})
    if len(compact.prompt_json()) > max_chars:
        raise ValueError("evidence context exceeds the configured input budget")
    return compact


def _summarize(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "[depth-limited]"
    if isinstance(value, dict):
        return {
            str(key)[:160]: _summarize(item, depth=depth + 1)
            for key, item in list(value.items())[:50]
        }
    if isinstance(value, list):
        return [_summarize(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, str):
        return value[:1000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1000]
