from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import DomainError


@dataclass(slots=True)
class AssistantBudget:
    max_model_calls: int
    max_tool_calls: int
    max_total_tokens: int
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    def require_model_capacity(self) -> None:
        if self.model_calls >= self.max_model_calls:
            raise DomainError(
                "LLM_BUDGET_EXCEEDED",
                "本轮模型调用次数已达到上限",
                409,
            )

    def record_model_call(self, *, input_tokens: int, output_tokens: int, latency_ms: int) -> None:
        self.require_model_capacity()
        if (
            self.input_tokens + self.output_tokens + input_tokens + output_tokens
            > self.max_total_tokens
        ):
            raise DomainError(
                "LLM_BUDGET_EXCEEDED",
                "本轮模型 Token 用量已达到上限",
                409,
            )
        self.model_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.latency_ms += latency_ms

    def reserve_tool_call(self) -> None:
        if self.tool_calls >= self.max_tool_calls:
            raise DomainError(
                "LLM_TOOL_BUDGET_EXCEEDED",
                "本轮工具调用次数已达到上限",
                409,
            )
        self.tool_calls += 1
