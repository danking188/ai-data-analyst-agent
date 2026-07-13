from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class LLMResponse[ResponseT: BaseModel]:
    provider: str
    model: str
    request_id: str | None
    content: ResponseT
    usage: LLMUsage
    finish_reason: str
    latency_ms: int


class LLMProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class LLMProvider(Protocol):
    def generate_structured[ResponseT: BaseModel](
        self,
        *,
        messages: list[LLMMessage],
        response_schema: type[ResponseT],
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> LLMResponse[ResponseT]: ...


@dataclass(frozen=True, slots=True)
class FakeLLMCall:
    messages: tuple[LLMMessage, ...]
    schema_name: str
    model: str
    temperature: float
    timeout_seconds: int
    max_output_tokens: int


class FakeLLMProvider:
    """Deterministic provider used by unit, integration, and offline evaluation tests."""

    def __init__(self, responses: Iterable[dict[str, object]]) -> None:
        self._responses = list(responses)
        self.calls: list[FakeLLMCall] = []

    def generate_structured[ResponseT: BaseModel](
        self,
        *,
        messages: list[LLMMessage],
        response_schema: type[ResponseT],
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> LLMResponse[ResponseT]:
        self.calls.append(
            FakeLLMCall(
                messages=tuple(messages),
                schema_name=response_schema.__name__,
                model=model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
            )
        )
        if not self._responses:
            raise LLMProviderError(
                "LLM_FAKE_RESPONSE_EXHAUSTED",
                "Fake LLM provider has no queued response",
                retryable=False,
            )
        raw = self._responses.pop(0)
        try:
            content = response_schema.model_validate(raw)
        except ValidationError as exc:
            raise LLMProviderError(
                "LLM_INVALID_RESPONSE",
                "Fake LLM response does not match the required schema",
                retryable=False,
            ) from exc
        return LLMResponse(
            provider="fake",
            model=model,
            request_id=f"fake-{len(self.calls)}",
            content=content,
            usage=LLMUsage(input_tokens=0, output_tokens=0),
            finish_reason="stop",
            latency_ms=0,
        )
