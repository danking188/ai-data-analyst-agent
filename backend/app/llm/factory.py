from __future__ import annotations

from functools import lru_cache
from typing import cast

from app.core.config import get_settings
from app.llm.openai_compatible import OpenAICompatibleProvider, StructuredOutputMode
from app.llm.provider import FakeLLMProvider, LLMProvider


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "fake":
        return FakeLLMProvider([])
    if not settings.llm_api_base or not settings.llm_api_key:
        raise RuntimeError("enabled OpenAI-compatible provider is not configured")
    return OpenAICompatibleProvider(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        structured_output_mode=cast(StructuredOutputMode, settings.llm_structured_output_mode),
        max_retries=settings.llm_max_retries,
    )
