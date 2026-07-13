from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictLLMModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantIntent(StrictLLMModel):
    intent: Literal[
        "answer_from_evidence",
        "inspect_data",
        "plan_analysis",
        "draft_cleaning",
        "explain_model",
        "export_report",
        "clarify",
        "refuse",
    ]
    rationale: str = Field(min_length=1, max_length=1000)
    requires_new_computation: bool


class AssistantPlanStep(StrictLLMModel):
    position: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    tool_name: str | None = Field(default=None, max_length=160)
    purpose: str = Field(min_length=1, max_length=1000)
    requires_confirmation: bool


class AssistantPlan(StrictLLMModel):
    objective: str = Field(min_length=1, max_length=2000)
    dataset_version_id: str | None = None
    steps: list[AssistantPlanStep] = Field(min_length=1, max_length=12)
    estimated_model_calls: int = Field(ge=0, le=4)
    estimated_tool_calls: int = Field(ge=0, le=8)
    limitations: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def positions_are_contiguous(self) -> AssistantPlan:
        if [step.position for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("plan step positions must be contiguous and start at 1")
        return self


class AssistantFinding(StrictLLMModel):
    text: str = Field(min_length=1, max_length=4000)
    claim_level: int = Field(ge=1, le=5)
    citation_ids: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class AssistantNextAction(StrictLLMModel):
    label: str = Field(min_length=1, max_length=160)
    action_type: Literal[
        "ask",
        "draft_spec",
        "run_analysis",
        "draft_cleaning",
        "export_report",
    ]
    requires_confirmation: bool


class AssistantAnswer(StrictLLMModel):
    summary: str = Field(min_length=1, max_length=8000)
    findings: list[AssistantFinding] = Field(default_factory=list, max_length=50)
    next_actions: list[AssistantNextAction] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=20)
