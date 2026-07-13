from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from app.llm.context import EvidenceContext
from app.llm.schemas import AssistantAnswer

NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")
CAUSAL_PATTERN = re.compile(
    r"(?:导致|造成|引起|因果|驱动了|cause[ds]?|causal|result(?:s|ed)? in)",
    re.IGNORECASE,
)


class CitationValidationError(ValueError):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


def validate_evidence_answer(answer: AssistantAnswer, context: EvidenceContext) -> None:
    sources: dict[str, str] = {claim.claim_id: claim.text for claim in context.claims} | {
        artifact.artifact_id: json.dumps(artifact.result, ensure_ascii=False, default=str)
        for artifact in context.artifacts
    }
    messages: list[str] = []
    validated_finding_numbers: set[str] = set()
    for index, finding in enumerate(answer.findings, start=1):
        if not finding.citation_ids:
            messages.append(f"finding {index} has no evidence citation")
            continue
        unknown = [citation for citation in finding.citation_ids if citation not in sources]
        if unknown:
            messages.append(f"finding {index} references unknown evidence: {', '.join(unknown)}")
            continue
        source_numbers = {
            normalized
            for citation in finding.citation_ids
            for normalized in _normalized_numbers(sources[citation])
        }
        finding_numbers = _normalized_numbers(finding.text)
        missing_numbers = sorted(finding_numbers - source_numbers)
        if missing_numbers:
            messages.append(
                f"finding {index} contains unsupported numbers: {', '.join(missing_numbers)}"
            )
        else:
            validated_finding_numbers.update(finding_numbers)
        if not context.causal_interpretation_allowed and CAUSAL_PATTERN.search(finding.text):
            messages.append(f"finding {index} uses causal language without permission")

    summary_numbers = _normalized_numbers(answer.summary)
    unsupported_summary = sorted(summary_numbers - validated_finding_numbers)
    if unsupported_summary:
        messages.append(
            "summary contains numbers not established by a cited finding: "
            + ", ".join(unsupported_summary)
        )
    if not context.causal_interpretation_allowed and CAUSAL_PATTERN.search(answer.summary):
        messages.append("summary uses causal language without permission")
    if messages:
        raise CitationValidationError(messages)


def validate_answer_sources(
    answer: AssistantAnswer,
    sources: dict[str, str],
    *,
    causal_interpretation_allowed: bool = False,
) -> None:
    """Validate an assistant answer against project-bound tool output sources."""
    messages: list[str] = []
    validated_finding_numbers: set[str] = set()
    for index, finding in enumerate(answer.findings, start=1):
        if not finding.citation_ids:
            messages.append(f"finding {index} has no evidence citation")
            continue
        unknown = [citation for citation in finding.citation_ids if citation not in sources]
        if unknown:
            messages.append(f"finding {index} references unknown evidence: {', '.join(unknown)}")
            continue
        source_numbers = {
            normalized
            for citation in finding.citation_ids
            for normalized in _normalized_numbers(sources[citation])
        }
        finding_numbers = _normalized_numbers(finding.text)
        missing_numbers = sorted(finding_numbers - source_numbers)
        if missing_numbers:
            messages.append(
                f"finding {index} contains unsupported numbers: {', '.join(missing_numbers)}"
            )
        else:
            validated_finding_numbers.update(finding_numbers)
        if not causal_interpretation_allowed and CAUSAL_PATTERN.search(finding.text):
            messages.append(f"finding {index} uses causal language without permission")
    unsupported_summary = sorted(_normalized_numbers(answer.summary) - validated_finding_numbers)
    if unsupported_summary:
        messages.append(
            "summary contains numbers not established by a cited finding: "
            + ", ".join(unsupported_summary)
        )
    if not causal_interpretation_allowed and CAUSAL_PATTERN.search(answer.summary):
        messages.append("summary uses causal language without permission")
    if messages:
        raise CitationValidationError(messages)


def _normalized_numbers(text: str) -> set[str]:
    return {_normalize_number(token) for token in NUMBER_PATTERN.findall(text)}


def _normalize_number(token: str) -> str:
    suffix = "%" if token.endswith("%") else ""
    value = token.removesuffix("%")
    try:
        normalized = Decimal(value).normalize()
    except InvalidOperation:
        return token
    return f"{normalized}{suffix}"
