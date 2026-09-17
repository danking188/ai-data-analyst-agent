from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import DomainError


class CapabilityRisk(StrEnum):
    READ = "read"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_WRITE = "irreversible_write"


@dataclass(frozen=True, slots=True)
class ToolCapability:
    tool_name: str
    risk: CapabilityRisk
    project_bound: bool
    requires_confirmation: bool
    supports_dry_run: bool


CAPABILITIES = {
    capability.tool_name: capability
    for capability in (
        ToolCapability("project.get_context", CapabilityRisk.READ, True, False, False),
        ToolCapability("schema.get", CapabilityRisk.READ, True, False, False),
        ToolCapability("semantic.list_metrics", CapabilityRisk.READ, True, False, False),
        ToolCapability("quality.list_issues", CapabilityRisk.READ, True, False, False),
        ToolCapability("artifact.search", CapabilityRisk.READ, True, False, False),
        ToolCapability("claim.search", CapabilityRisk.READ, True, False, False),
        ToolCapability("run.get_status", CapabilityRisk.READ, True, False, False),
        ToolCapability("analysis.draft_spec", CapabilityRisk.REVERSIBLE_WRITE, True, True, True),
        ToolCapability("analysis.run", CapabilityRisk.REVERSIBLE_WRITE, True, True, True),
        ToolCapability("cleaning.draft_plan", CapabilityRisk.REVERSIBLE_WRITE, True, True, True),
        ToolCapability("cleaning.execute", CapabilityRisk.REVERSIBLE_WRITE, True, True, True),
        ToolCapability(
            "feature_engineering.suggest", CapabilityRisk.REVERSIBLE_WRITE, True, True, True
        ),
        ToolCapability("report.export", CapabilityRisk.REVERSIBLE_WRITE, True, True, True),
    )
}


def require_tool_capability(
    tool_name: str, *, expected_risk: CapabilityRisk, confirmed: bool
) -> ToolCapability:
    capability = CAPABILITIES.get(tool_name)
    if capability is None or capability.risk != expected_risk or not capability.project_bound:
        raise DomainError(
            "LLM_TOOL_NOT_ALLOWED",
            "工具没有匹配当前执行阶段的最小权限声明",
            409,
            details={"tool_name": tool_name},
        )
    if capability.requires_confirmation and not confirmed:
        raise DomainError(
            "LLM_CONFIRMATION_REQUIRED",
            "写操作必须在执行前获得用户确认",
            409,
            details={"tool_name": tool_name},
        )
    return capability
