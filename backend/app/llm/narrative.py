from __future__ import annotations

import json

from app.llm.citations import CitationValidationError, validate_evidence_answer
from app.llm.context import EvidenceContext
from app.llm.prompts import get_prompt
from app.llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMUsage
from app.llm.schemas import AssistantAnswer

PROMPT_NAME = "assistant.report_narrative"
PROMPT_VERSION = "1.1.0"
CORRECTION_PROMPT_NAME = "assistant.report_narrative_correction"
CORRECTION_PROMPT_VERSION = "1.0.0"


def generate_evidence_narrative(
    *,
    provider: LLMProvider,
    context: EvidenceContext,
    model: str,
    temperature: float,
    timeout_seconds: int,
    max_output_tokens: int,
) -> LLMResponse[AssistantAnswer]:
    prompt = get_prompt(PROMPT_NAME, PROMPT_VERSION)
    response = provider.generate_structured(
        messages=[
            LLMMessage(role="system", content=prompt.system),
            LLMMessage(
                role="user",
                content=(
                    "Create a concise evidence-based interpretation of this completed analysis. "
                    "Every finding must cite one or more supplied claim_id or artifact_id. "
                    "Do not include a number in the summary unless it also appears in a "
                    "cited finding.\n" + context.prompt_json()
                ),
            ),
        ],
        response_schema=AssistantAnswer,
        model=model,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
    )
    try:
        validate_evidence_answer(response.content, context)
        return response
    except CitationValidationError as exc:
        correction_prompt = get_prompt(CORRECTION_PROMPT_NAME, CORRECTION_PROMPT_VERSION)
        corrected = provider.generate_structured(
            messages=[
                LLMMessage(role="system", content=correction_prompt.system),
                LLMMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "task": "Correct the rejected evidence narrative.",
                            "validation_errors": exc.messages,
                            "invalid_draft": response.content.model_dump(mode="json"),
                            "evidence_context": json.loads(context.prompt_json()),
                            "rules": [
                                "Every finding must cite supplied claim_id or artifact_id values.",
                                "Every numeric token must occur verbatim in at least one cited "
                                "source.",
                                "Keep signed differences signed; do not rewrite -0.1 as a "
                                "decrease of 0.1.",
                                "A summary number must also occur in a valid cited finding.",
                                "Remove unsupported numbers and causal language.",
                            ],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            ],
            response_schema=AssistantAnswer,
            model=model,
            temperature=0,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        validate_evidence_answer(corrected.content, context)
        return LLMResponse(
            provider=corrected.provider,
            model=corrected.model,
            request_id=corrected.request_id,
            content=corrected.content,
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens + corrected.usage.input_tokens,
                output_tokens=response.usage.output_tokens + corrected.usage.output_tokens,
            ),
            finish_reason=corrected.finish_reason,
            latency_ms=response.latency_ms + corrected.latency_ms,
        )
