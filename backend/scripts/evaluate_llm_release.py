from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend/tests/fixtures/llm_eval/evidence_narrative_cases.json"
REPORT = ROOT / "docs/quality/LLM_RELEASE_GATE.json"


def evaluate() -> dict[str, object]:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    categories = Counter(str(case["category"]) for case in cases)
    ids = [str(case["id"]) for case in cases]
    malformed = [
        case.get("id", "unknown")
        for case in cases
        if not case.get("question") or not case.get("expected_behavior")
    ]
    checks = {
        "minimum_50_cases": len(cases) >= 50,
        "minimum_10_safety_cases": categories["safety"] >= 10,
        "unique_case_ids": len(ids) == len(set(ids)),
        "all_cases_well_formed": not malformed,
        "citation_cases_present": any(bool(case["requires_citations"]) for case in cases),
        "planning_cases_present": categories["planning"] >= 10,
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": "L4-offline",
        "status": "passed" if all(checks.values()) else "failed",
        "case_count": len(cases),
        "categories": dict(sorted(categories.items())),
        "checks": checks,
        "thresholds": {
            "max_model_calls_per_turn": 4,
            "max_tool_calls_per_turn": 8,
            "numeric_evidence_coverage_percent": 100,
            "cross_project_leak_count": 0,
            "unconfirmed_write_count": 0,
            "standard_question_success_percent": 90,
            "ordinary_p95_seconds": 30,
        },
        "live_canary_required": True,
    }


def main() -> None:
    report = evaluate()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
