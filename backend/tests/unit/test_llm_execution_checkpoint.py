from types import SimpleNamespace

import pytest

from app.domain.errors import DomainError
from app.workers.assistant import AssistantTurnWorker


def test_execution_checkpoint_restores_child_job_without_recreating_resource() -> None:
    call = SimpleNamespace(
        tool_name="analysis.run",
        result_resource_type="analysis_run",
        result_resource_id="run_existing",
        result_json={
            "run_id": "run_existing",
            "job_id": "job_existing",
            "_execution_checkpoint": {
                "tool_name": "analysis.run",
                "child_job_id": "job_existing",
                "child_job_kind": "analysis_run",
            },
        },
    )
    execution = AssistantTurnWorker._execution_from_checkpoint(call)
    assert execution.resource_id == "run_existing"
    assert execution.child_job_id == "job_existing"
    assert execution.result == {"run_id": "run_existing", "job_id": "job_existing"}


def test_execution_checkpoint_rejects_tool_identity_mismatch() -> None:
    call = SimpleNamespace(
        tool_name="analysis.run",
        result_resource_type="analysis_run",
        result_resource_id="run_existing",
        result_json={"_execution_checkpoint": {"tool_name": "report.export"}},
    )
    with pytest.raises(DomainError) as captured:
        AssistantTurnWorker._execution_from_checkpoint(call)
    assert captured.value.code == "ASSISTANT_EXECUTION_CHECKPOINT_INVALID"
