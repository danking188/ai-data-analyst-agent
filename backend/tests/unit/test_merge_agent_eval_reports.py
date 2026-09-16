from scripts.merge_agent_eval_reports import merge_reports


def _result(case_id: str, elapsed_ms: int) -> dict:
    return {
        "case_id": case_id,
        "category": "eda",
        "passed": True,
        "hard_rules_passed": True,
        "task_rules_passed": True,
        "judge_score": None,
        "elapsed_ms": elapsed_ms,
        "checks": [
            {
                "name": "no_unconfirmed_write",
                "layer": "hard",
                "passed": True,
                "detail": "none",
            }
        ],
        "observation": {
            "message_status": "completed",
            "job_status": "succeeded",
            "answer": {"summary": "ok"},
            "elapsed_ms": elapsed_ms,
        },
    }


def test_merge_reports_replaces_only_scoped_cases_and_recalculates_latency() -> None:
    base = {
        "gate": "agent-eval-live-full",
        "candidate": "base",
        "generated_at": "2026-09-16T00:00:00+00:00",
        "results": [_result("eda-01", 40_000), _result("eda-02", 10_000)],
    }
    delta = {
        "candidate": "delta",
        "generated_at": "2026-09-16T01:00:00+00:00",
        "results": [_result("eda-01", 4_000)],
    }

    merged = merge_reports(base, [delta], candidate="final")

    assert merged["status"] == "passed"
    assert merged["summary"]["p95_latency_ms"] == 10_000
    assert merged["replaced_case_ids"] == ["eda-01"]
    assert merged["verification_lineage"][1]["case_ids"] == ["eda-01"]
