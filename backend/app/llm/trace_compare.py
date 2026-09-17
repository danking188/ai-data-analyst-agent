from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from app.api.schemas import AssistantReplayCandidate, AssistantReplayCandidateResult
from app.llm.citations import CitationValidationError, validate_answer_sources
from app.llm.prompts import EVIDENCE_BOUNDARY
from app.llm.provider import LLMMessage, LLMProvider
from app.llm.schemas import AssistantAnswer

VARIANT_INSTRUCTIONS = {
    "current": "Separate findings, limitations, and next actions.",
    "concise": "Answer concisely. Keep only decision-relevant verified findings.",
    "evidence_auditor": (
        "Act as an evidence auditor. Prefer limitations over unsupported claims and explain "
        "when the supplied evidence cannot answer the question."
    ),
}


def compare_candidate(
    *,
    provider: LLMProvider,
    candidate: AssistantReplayCandidate,
    default_model: str,
    question: str,
    recorded_tool_results: list[dict[str, Any]],
    original_answer: AssistantAnswer | None,
    timeout_seconds: int,
    max_output_tokens: int,
    max_input_chars: int = 60000,
) -> AssistantReplayCandidateResult:
    model = candidate.model or default_model
    bounded_results = _bounded_results(recorded_tool_results, max_chars=max_input_chars)
    sources = _citation_sources(bounded_results)
    response = provider.generate_structured(
        messages=[
            LLMMessage(
                role="system",
                content=EVIDENCE_BOUNDARY + "\n" + VARIANT_INSTRUCTIONS[candidate.prompt_variant],
            ),
            LLMMessage(
                role="user",
                content=json.dumps(
                    {
                        "task": "Replay the answer using recorded tool results only.",
                        "question": question,
                        "recorded_tool_results": bounded_results,
                        "allowed_citation_ids": sorted(sources),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            ),
        ],
        response_schema=AssistantAnswer,
        model=model,
        temperature=0,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
    )
    error: str | None = None
    try:
        validate_answer_sources(response.content, sources)
    except CitationValidationError as exc:
        error = str(exc)
    original_summary = original_answer.summary if original_answer else ""
    similarity = SequenceMatcher(None, original_summary, response.content.summary).ratio()
    return AssistantReplayCandidateResult(
        label=candidate.label,
        model=model,
        prompt_variant=candidate.prompt_variant,
        answer=response.content,
        citation_valid=error is None,
        validation_error=error,
        similarity_to_original=round(similarity, 4),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=response.latency_ms,
    )


def _citation_sources(results: list[dict[str, Any]]) -> dict[str, str]:
    sources: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            identifiers = [
                item for key, item in value.items() if key.endswith("_id") and isinstance(item, str)
            ]
            rendered = json.dumps(value, ensure_ascii=False, default=str)
            for identifier in identifiers:
                sources[identifier] = rendered
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(results)
    return sources


def _bounded_results(results: list[dict[str, Any]], *, max_chars: int) -> list[dict[str, Any]]:
    if max_chars <= 0:
        raise ValueError("max_input_chars must be positive")
    encoded = json.dumps(results, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return results
    compact = [
        {
            "tool_call_id": item.get("tool_call_id"),
            "tool_name": item.get("tool_name"),
            "result_resource_type": item.get("result_resource_type"),
            "result_resource_id": item.get("result_resource_id"),
            "result": {"omitted": "replay_context_budget"},
        }
        for item in results[:50]
    ]
    if len(json.dumps(compact, ensure_ascii=False, default=str)) > max_chars:
        raise ValueError("recorded replay context exceeds the configured input budget")
    return compact
