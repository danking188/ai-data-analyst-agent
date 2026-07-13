from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.llm.provider import FakeLLMProvider
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import (
    AnalysisRunRow,
    AnalysisSpecRow,
    ArtifactRow,
    ClaimRow,
    CleaningPlanRow,
)
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.session import get_database
from app.workers.assistant import AssistantTurnWorker
from tests.contract.test_dataset_contract import upload_csv


def _enable_worker_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("JOB_EXECUTION_MODE", "worker")
    get_settings.cache_clear()


def _upload(app_client, headers: dict[str, str], project_id: str, content: bytes, key: str) -> str:
    job = upload_csv(app_client, project_id, headers, key=key, content=content)
    completed = app_client.get(f"/api/v1/jobs/{job['job_id']}", headers=headers).json()
    assert completed["status"] == "succeeded", completed
    return str(completed["resource_id"])


def _conversation_and_turn(
    app_client,
    headers: dict[str, str],
    project_id: str,
    version_id: str,
    question: str,
    key: str,
) -> tuple[str, str, str]:
    conversation = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/conversations",
        headers={**headers, "Idempotency-Key": f"{key}-conversation"},
        json={"title": "真实数据 Copilot", "dataset_version_id": version_id},
    )
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["conversation_id"]
    turn = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
        headers={**headers, "Idempotency-Key": f"{key}-turn"},
        json={"content": question},
    )
    assert turn.status_code == 202, turn.text
    payload = turn.json()
    return conversation_id, payload["assistant_message"]["message_id"], payload["job"]["job_id"]


def _approve_and_run(app_client, headers: dict[str, str], project_id: str, message_id: str) -> str:
    key = f"approve-{message_id}"
    approved = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/confirm",
        headers={**headers, "Idempotency-Key": key},
        json={"decision": "approve", "tool_call_ids": []},
    )
    assert approved.status_code == 202, approved.text
    replay = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/confirm",
        headers={**headers, "Idempotency-Key": key},
        json={"decision": "approve", "tool_call_ids": []},
    )
    assert replay.status_code == 202
    assert replay.json() == approved.json()
    job_id = approved.json()["job"]["job_id"]
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="assistant-actions-confirmed",
        provider=FakeLLMProvider([]),
        settings=get_settings(),
    )
    assert worker.run(job_id) is True
    return approved.json()["assistant_message"]["message_id"]


def test_confirmed_analysis_plan_runs_real_modeling(
    app_client,
    auth_headers: dict[str, str],
    create_project,
    monkeypatch,
) -> None:
    project_id = str(create_project(key="assistant-analysis-project")["project_id"])
    rows = ["feature,segment,target"] + [
        f"{index},{'a' if index % 3 else 'b'},{'yes' if index % 2 else 'no'}"
        for index in range(1, 41)
    ]
    version_id = _upload(
        app_client,
        auth_headers,
        project_id,
        ("\n".join(rows) + "\n").encode(),
        "assistant-analysis-source",
    )
    _enable_worker_mode(monkeypatch)
    conversation_id, message_id, job_id = _conversation_and_turn(
        app_client,
        auth_headers,
        project_id,
        version_id,
        "用 target 训练一个可复现的二分类模型，并比较候选模型",
        "assistant-analysis",
    )
    provider = FakeLLMProvider(
        [
            {
                "intent": "plan_analysis",
                "rationale": "需要新的建模运行",
                "requires_new_computation": True,
            },
            {
                "objective": "建立并运行二分类基线",
                "dataset_version_id": version_id,
                "steps": [
                    {
                        "position": 1,
                        "title": "草拟分析规格",
                        "tool_name": "analysis.draft_spec",
                        "purpose": "确认目标、特征、拆分和指标",
                        "requires_confirmation": True,
                    },
                    {
                        "position": 2,
                        "title": "运行候选模型",
                        "tool_name": "analysis.run",
                        "purpose": "训练并评估真实模型",
                        "requires_confirmation": True,
                    },
                    {
                        "position": 3,
                        "title": "生成特征工程建议",
                        "tool_name": "feature_engineering.suggest",
                        "purpose": "给出不执行任意代码的候选特征建议",
                        "requires_confirmation": True,
                    },
                ],
                "estimated_model_calls": 4,
                "estimated_tool_calls": 3,
                "limitations": [],
            },
            {
                "name": "Assistant 二分类",
                "task": "binary_classification",
                "target": "target",
                "entity_key": None,
                "time_column": None,
                "prediction_time_description": "使用观测时已经可用的字段预测 target",
                "split_strategy": "stratified",
                "group_column": None,
                "metrics": ["accuracy", "f1", "roc_auc"],
                "included_columns": ["feature", "segment"],
                "excluded_columns": [],
                "random_seed": 42,
                "rationale": "目标为二元类别，使用分层拆分",
                "leakage_warnings": [],
            },
            {
                "title": "二分类特征工程建议",
                "suggestions": [
                    {
                        "name": "feature_log",
                        "source_columns": ["feature"],
                        "transformation": "log_transform",
                        "rationale": "数值跨度可用对数变换降低偏斜影响",
                        "leakage_risk": "low",
                        "leakage_note": "仅使用预测时点已知的 feature",
                    }
                ],
                "limitations": ["建议不会自动生成或执行代码"],
            },
        ]
    )
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="assistant-actions-plan",
        provider=provider,
        settings=get_settings(),
    )
    assert worker.run(job_id) is True

    session = get_database().session()
    try:
        repository = AssistantRepository(session)
        message = repository.get_message(project_id=project_id, message_id=message_id)
        calls = repository.list_tool_calls(
            repository.latest_llm_run_for_message(message_id).llm_run_id
        )  # type: ignore[union-attr]
        assert message.status == "awaiting_confirmation"
        assert calls[0].arguments_json["target"] == "target"
        assert calls[0].arguments_json["metrics"] == ["accuracy", "f1", "roc_auc"]
        assert (
            session.scalar(select(AnalysisSpecRow).where(AnalysisSpecRow.project_id == project_id))
            is None
        )
        spec_call_id = calls[0].tool_call_id
        edited_arguments = {**calls[0].arguments_json, "random_seed": 7}
    finally:
        session.close()

    invalid = app_client.patch(
        f"/api/v1/projects/{project_id}/assistant/tool-calls/{spec_call_id}",
        headers=auth_headers,
        json={"arguments": {**edited_arguments, "target": "not_a_column"}},
    )
    assert invalid.status_code == 422
    edited = app_client.patch(
        f"/api/v1/projects/{project_id}/assistant/tool-calls/{spec_call_id}",
        headers=auth_headers,
        json={"arguments": edited_arguments},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["arguments"]["random_seed"] == 7
    other_project_id = str(create_project(key="assistant-analysis-other-project")["project_id"])
    cross_project = app_client.patch(
        f"/api/v1/projects/{other_project_id}/assistant/tool-calls/{spec_call_id}",
        headers=auth_headers,
        json={"arguments": edited_arguments},
    )
    assert cross_project.status_code == 404

    changed = app_client.patch(
        f"/api/v1/projects/{project_id}/assistant/conversations/{conversation_id}",
        headers=auth_headers,
        json={"dataset_version_id": None},
    )
    assert changed.status_code == 200
    stale_confirmation = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/messages/{message_id}/confirm",
        headers={**auth_headers, "Idempotency-Key": "stale-version-confirm"},
        json={"decision": "approve", "tool_call_ids": []},
    )
    assert stale_confirmation.status_code == 409
    restored = app_client.patch(
        f"/api/v1/projects/{project_id}/assistant/conversations/{conversation_id}",
        headers=auth_headers,
        json={"dataset_version_id": version_id},
    )
    assert restored.status_code == 200

    continuation_id = _approve_and_run(app_client, auth_headers, project_id, message_id)
    session = get_database().session()
    try:
        repository = AssistantRepository(session)
        continuation = repository.get_message(project_id=project_id, message_id=continuation_id)
        spec = session.scalar(
            select(AnalysisSpecRow).where(AnalysisSpecRow.project_id == project_id)
        )
        run = session.scalar(select(AnalysisRunRow).where(AnalysisRunRow.project_id == project_id))
        feature_artifact = session.scalar(
            select(ArtifactRow).where(
                ArtifactRow.project_id == project_id,
                ArtifactRow.producer == "feature_engineering.suggest",
            )
        )
        model_artifact = session.scalar(
            select(ArtifactRow).where(
                ArtifactRow.project_id == project_id,
                ArtifactRow.type == "model",
            )
        )
        claim = session.scalar(select(ClaimRow).where(ClaimRow.project_id == project_id))
        assert continuation.status == "completed", continuation.content
        assert spec is not None and spec.status == "confirmed" and spec.random_seed == 7
        assert run is not None and run.status == "succeeded"
        assert feature_artifact is not None
        assert feature_artifact.result_json["suggestions"][0]["transformation"] == "log_transform"
        assert model_artifact is not None and claim is not None
        assert "真实分析与建模运行已完成" in (continuation.content or "")
        model_artifact_id = model_artifact.artifact_id
        claim_id = claim.claim_id
    finally:
        session.close()
    frozen = app_client.patch(
        f"/api/v1/projects/{project_id}/assistant/tool-calls/{spec_call_id}",
        headers=auth_headers,
        json={"arguments": edited_arguments},
    )
    assert frozen.status_code == 409

    explanation_turn = app_client.post(
        f"/api/v1/projects/{project_id}/assistant/conversations/{conversation_id}/messages",
        headers={**auth_headers, "Idempotency-Key": "assistant-model-explanation"},
        json={"content": "解释刚才模型的结果、限制和证据"},
    )
    assert explanation_turn.status_code == 202, explanation_turn.text
    explanation_payload = explanation_turn.json()
    explanation_worker = AssistantTurnWorker(
        get_database(),
        worker_id="assistant-model-explanation",
        provider=FakeLLMProvider(
            [
                {
                    "intent": "explain_model",
                    "rationale": "读取真实模型 Artifact 与 Claim",
                    "requires_new_computation": False,
                },
                {
                    "summary": "模型解释已绑定本次真实运行的证据。",
                    "findings": [
                        {
                            "text": "候选模型已完成保留集评估，结论应结合已记录限制理解。",
                            "claim_level": 3,
                            "citation_ids": [model_artifact_id, claim_id],
                            "limitations": ["相关性和预测贡献不代表因果关系"],
                        }
                    ],
                    "next_actions": [],
                    "limitations": ["解释只使用当前项目已验证的证据"],
                },
            ]
        ),
        settings=get_settings(),
    )
    assert explanation_worker.run(explanation_payload["job"]["job_id"]) is True
    session = get_database().session()
    try:
        explanation = AssistantRepository(session).get_message(
            project_id=project_id,
            message_id=explanation_payload["assistant_message"]["message_id"],
        )
        citations = explanation.content_json["answer"]["findings"][0]["citation_ids"]
        assert explanation.status == "completed"
        assert citations == [model_artifact_id, claim_id]
    finally:
        session.close()


def test_confirmed_cleaning_plan_previews_and_creates_new_version(
    app_client,
    auth_headers: dict[str, str],
    create_project,
    monkeypatch,
) -> None:
    project_id = str(create_project(key="assistant-cleaning-project")["project_id"])
    version_id = _upload(
        app_client,
        auth_headers,
        project_id,
        b"name,value\nalice,1\nbob,\nbob,\n",
        "assistant-cleaning-source",
    )
    _enable_worker_mode(monkeypatch)
    _, message_id, job_id = _conversation_and_turn(
        app_client,
        auth_headers,
        project_id,
        version_id,
        "填补 value 缺失值并删除重复记录，先预览再执行",
        "assistant-cleaning",
    )
    provider = FakeLLMProvider(
        [
            {
                "intent": "draft_cleaning",
                "rationale": "需要受控清洗",
                "requires_new_computation": True,
            },
            {
                "objective": "填补缺失并去重",
                "dataset_version_id": version_id,
                "steps": [
                    {
                        "position": 1,
                        "title": "草拟并预览清洗计划",
                        "tool_name": "cleaning.draft_plan",
                        "purpose": "使用确定性引擎计算影响",
                        "requires_confirmation": True,
                    },
                    {
                        "position": 2,
                        "title": "执行清洗",
                        "tool_name": "cleaning.execute",
                        "purpose": "生成新的版本化数据集",
                        "requires_confirmation": True,
                    },
                ],
                "estimated_model_calls": 3,
                "estimated_tool_calls": 2,
                "limitations": [],
            },
            {
                "name": "缺失与重复清洗",
                "operations": [
                    {
                        "operation": "impute_missing",
                        "column": "value",
                        "parameters": {"method": "constant", "value": 0},
                        "reason": "value 存在缺失",
                        "issue_ids": [],
                        "risk_level": "low",
                        "reversible": True,
                    },
                    {
                        "operation": "drop_duplicates",
                        "column": None,
                        "parameters": {"columns": ["name", "value"], "keep": "first"},
                        "reason": "删除完全重复记录",
                        "issue_ids": [],
                        "risk_level": "high",
                        "reversible": False,
                    },
                ],
                "rationale": "先填补再去重，影响由预览计算",
                "limitations": [],
            },
        ]
    )
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="assistant-cleaning-plan",
        provider=provider,
        settings=get_settings(),
    )
    assert worker.run(job_id) is True
    continuation_id = _approve_and_run(app_client, auth_headers, project_id, message_id)

    session = get_database().session()
    try:
        plan = session.scalar(
            select(CleaningPlanRow).where(CleaningPlanRow.project_id == project_id)
        )
        continuation = AssistantRepository(session).get_message(
            project_id=project_id, message_id=continuation_id
        )
        versions = list(
            session.scalars(
                select(DatasetVersionRow).where(DatasetVersionRow.project_id == project_id)
            )
        )
        assert plan is not None and plan.status == "executed"
        assert plan.preview_artifact_id is not None
        assert plan.result_version_id is not None and plan.result_version_id != version_id
        assert any(
            row.version_id == plan.result_version_id and row.status == "ready" for row in versions
        )
        assert continuation.status == "completed"
        assert "生成新数据版本" in (continuation.content or "")
    finally:
        session.close()
