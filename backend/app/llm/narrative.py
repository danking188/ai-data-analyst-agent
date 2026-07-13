from __future__ import annotations

from app.llm.citations import validate_evidence_answer
from app.llm.context import EvidenceContext
from app.llm.prompts import get_prompt
from app.llm.provider import LLMMessage, LLMProvider, LLMResponse
from app.llm.schemas import AssistantAnswer

PROMPT_NAME = "assistant.report_narrative"
PROMPT_VERSION = "1.0.0"


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
    validate_evidence_answer(response.content, context)
    return response
