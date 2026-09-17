import pytest

from app.domain.errors import DomainError
from app.llm.capabilities import CapabilityRisk, require_tool_capability


def test_capability_model_enforces_risk_and_confirmation() -> None:
    read = require_tool_capability(
        "schema.get", expected_risk=CapabilityRisk.READ, confirmed=False
    )
    assert read.project_bound is True
    with pytest.raises(DomainError) as unconfirmed:
        require_tool_capability(
            "analysis.run",
            expected_risk=CapabilityRisk.REVERSIBLE_WRITE,
            confirmed=False,
        )
    assert unconfirmed.value.code == "LLM_CONFIRMATION_REQUIRED"
    with pytest.raises(DomainError):
        require_tool_capability(
            "shell.exec", expected_risk=CapabilityRisk.IRREVERSIBLE_WRITE, confirmed=True
        )
