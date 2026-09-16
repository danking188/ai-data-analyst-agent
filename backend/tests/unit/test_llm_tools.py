from __future__ import annotations

import pytest

from app.domain.errors import DomainError
from app.llm.citations import validate_answer_sources
from app.llm.schemas import AssistantAnswer, AssistantIntent, AssistantPlan, AssistantPlanStep
from app.llm.tools import AssistantToolContext, AssistantToolRegistry, AssistantToolResult
from app.persistence.repositories.datasets import DatasetVersionDraft
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork
from app.workers.assistant import AssistantTurnWorker


def _plan(*tool_names: str) -> AssistantPlan:
    return AssistantPlan(
        objective="Prepare a controlled action.",
        dataset_version_id="dsv_1",
        steps=[
            AssistantPlanStep(
                position=index,
                title=tool_name,
                tool_name=tool_name,
                purpose=tool_name,
                requires_confirmation=True,
            )
            for index, tool_name in enumerate(tool_names, start=1)
        ],
        estimated_model_calls=2,
        estimated_tool_calls=len(tool_names),
        limitations=[],
    )


def test_agent_normalizes_high_risk_edge_intents_and_minimal_plans() -> None:
    unsafe_refusal = AssistantIntent(
        intent="refuse", rationale="causal wording", requires_new_computation=False
    )
    causal = AssistantTurnWorker._normalize_intent(
        "把相关性写成导致结果的原因。", unsafe_refusal
    )
    missing_target = AssistantTurnWorker._normalize_intent(
        "在没有目标列时训练模型。",
        AssistantIntent(
            intent="plan_analysis", rationale="train", requires_new_computation=True
        ),
    )
    quality = AssistantTurnWorker._normalize_intent(
        "异常值被如何处理？",
        AssistantIntent(
            intent="explain_model", rationale="model preprocessing", requires_new_computation=False
        ),
    )
    extrapolation = AssistantTurnWorker._normalize_intent(
        "能否据此预测未来所有时间段？",
        AssistantIntent(intent="clarify", rationale="ambiguous", requires_new_computation=False),
    )
    feature_plan = AssistantTurnWorker._normalize_plan(
        "对 customer_id 做特征工程。",
        AssistantIntent(
            intent="plan_analysis", rationale="feature", requires_new_computation=True
        ),
        _plan("analysis.draft_spec", "analysis.run"),
    )
    training_plan = AssistantTurnWorker._normalize_plan(
        "为是否流失训练分类模型。",
        AssistantIntent(
            intent="plan_analysis", rationale="train", requires_new_computation=True
        ),
        _plan("cleaning.draft_plan", "analysis.draft_spec", "analysis.run"),
    )

    assert causal.intent == "answer_from_evidence"
    assert missing_target.intent == "inspect_data"
    assert quality.intent == "inspect_data"
    assert extrapolation.intent == "answer_from_evidence"
    assert [step.tool_name for step in feature_plan.steps] == ["feature_engineering.suggest"]
    assert [step.tool_name for step in training_plan.steps] == ["analysis.draft_spec"]


def test_agent_adds_a_cited_causal_boundary() -> None:
    answer = AssistantAnswer(summary="找到相关分析。")

    bounded = AssistantTurnWorker._enforce_causal_boundary(
        "相关性是否导致结果？", answer, {"art_1": "persisted artifact"}
    )

    assert bounded.findings[0].citation_ids == ["art_1"]
    assert any("不能据此推断因果" in item for item in bounded.limitations)
    assert AssistantTurnWorker._is_causal_overclaim_request("分析能证明某字段导致结果吗？")


def test_read_only_tool_registry_is_project_bound(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session) as uow:
            first = uow.projects.create(
                name="First",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            second = uow.projects.create(
                name="Second",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-b",
            )
        registry = AssistantToolRegistry(session)
        result = registry.execute(
            "project.get_context",
            context=AssistantToolContext(first.project_id, None),
        )
        assert result.data["project"]["project_id"] == first.project_id
        assert result.data["project"]["name"] == "First"
        assert result.data["project"]["project_id"] != second.project_id
    finally:
        session.close()


def test_tool_registry_rejects_unknown_and_extra_arguments(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        project = ProjectRepository(session).create(
            name="Project",
            description=None,
            timezone="Asia/Shanghai",
            language="zh-CN",
            subject_id="user-a",
        )
        session.commit()
        registry = AssistantToolRegistry(session)
        with pytest.raises(DomainError, match="未被允许"):
            registry.execute(
                "shell.execute",
                context=AssistantToolContext(project.project_id, None),
            )
        with pytest.raises(ValueError):
            registry.execute(
                "project.get_context",
                context=AssistantToolContext(project.project_id, None),
                arguments={"url": "https://example.com"},
            )
    finally:
        session.close()


def test_project_context_exposes_dataset_shape_as_citable_evidence(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session) as uow:
            project = uow.projects.create(
                name="Citable context",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            dataset = uow.datasets.create_dataset(
                project_id=project.project_id,
                name="sample.csv",
                source_type="csv",
                subject_id="user-a",
            )
            version = uow.datasets.create_version(
                project_id=project.project_id,
                dataset_id=dataset.dataset_id,
                subject_id="user-a",
                draft=DatasetVersionDraft(
                    source_file_name="sample.csv",
                    source_type="csv",
                    source_storage_key="projects/test/source/sample.csv",
                    file_hash="sha256:" + "a" * 64,
                    file_size_bytes=100,
                ),
            )
            uow.datasets.mark_version_ready(
                version,
                data_storage_key="projects/test/versions/v1/data.parquet",
                data_checksum="sha256:" + "b" * 64,
                row_count=120,
                column_count=3,
            )

        result = AssistantToolRegistry(session).execute(
            "project.get_context",
            context=AssistantToolContext(project.project_id, version.version_id),
        )

        assert result.data["dataset_version"]["row_count"] == 120
        assert version.version_id in result.citation_sources
        assert "120" in result.citation_sources[version.version_id]
        assert result.resource_type == "dataset_version"
        assert result.resource_id == version.version_id
    finally:
        session.close()


def test_answer_prompt_projection_keeps_evidence_and_drops_bulk_charts() -> None:
    result = AssistantToolResult(
        tool_name="artifact.search",
        tool_version="1.0.0",
        data={
            "artifacts": [
                {
                    "artifact_id": "art_chart",
                    "type": "chart",
                    "name": "large chart",
                    "result": {"data": list(range(1000))},
                },
                {
                    "artifact_id": "art_metric",
                    "type": "metric",
                    "name": "holdout metrics",
                    "result": {"metrics": {"accuracy": 0.8}},
                },
            ]
        },
        citation_sources={"art_chart": "chart", "art_metric": "accuracy=0.8"},
    )

    projected = AssistantTurnWorker._tool_prompt_data(result)

    assert [item["artifact_id"] for item in projected["artifacts"]] == ["art_metric"]
    assert AssistantTurnWorker._tool_prompt_citation_ids(result) == ["art_metric"]


def test_deterministic_fallback_answers_model_and_distribution_questions() -> None:
    model_source = {
        "artifact_id": "art_model",
        "type": "model",
        "result": {"model_family": "ridge", "task": "regression"},
    }
    distribution_source = {
        "artifact_id": "art_distribution",
        "type": "comparison",
        "result": {
            "target_diagnostics": {
                "distribution": [
                    {"class": "yes", "count": 60, "rate": 0.5},
                    {"class": "no", "count": 60, "rate": 0.5},
                ]
            }
        },
    }
    tools = [
        AssistantToolResult(
            tool_name="artifact.search",
            tool_version="1.0.0",
            data={"artifacts": [model_source, distribution_source]},
            citation_sources={
                "art_model": str(model_source),
                "art_distribution": str(distribution_source),
            },
        )
    ]

    model_answer = AssistantTurnWorker._deterministic_evidence_fallback(
        tools, question="最终选择了哪个回归模型？"
    )
    distribution_answer = AssistantTurnWorker._deterministic_evidence_fallback(
        tools, question="目标变量的分布是否均衡？"
    )

    validate_answer_sources(model_answer, tools[0].citation_sources)
    validate_answer_sources(distribution_answer, tools[0].citation_sources)
    assert "ridge" in model_answer.findings[0].text
    assert len(distribution_answer.findings) == 2
