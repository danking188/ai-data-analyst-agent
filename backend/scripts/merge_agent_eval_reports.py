#!/usr/bin/env python3
"""Merge a full Agent gate with scoped post-fix reruns and recalculate the gate."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.llm.evaluation import AgentEvalResult, summarize_agent_eval
from scripts.evaluate_llm_release import release_thresholds


def merge_reports(
    base: dict[str, Any],
    deltas: list[dict[str, Any]],
    *,
    candidate: str,
) -> dict[str, Any]:
    if base.get("gate") != "agent-eval-live-full":
        raise ValueError("base report must be a full live Agent gate")
    ordered_results = [AgentEvalResult.model_validate(item) for item in base["results"]]
    positions = {result.case_id: index for index, result in enumerate(ordered_results)}
    replaced: list[str] = []
    lineage = [
        {
            "role": "base_full",
            "candidate": base.get("candidate"),
            "generated_at": base.get("generated_at"),
            "case_count": len(ordered_results),
            "summary": base.get("summary"),
            "gate_checks": base.get("gate_checks"),
        }
    ]
    for delta in deltas:
        delta_results = [AgentEvalResult.model_validate(item) for item in delta["results"]]
        if not delta_results:
            raise ValueError("delta report must contain at least one result")
        unknown = sorted(
            result.case_id for result in delta_results if result.case_id not in positions
        )
        if unknown:
            raise ValueError(f"delta contains cases absent from base: {', '.join(unknown)}")
        if not all(result.passed for result in delta_results):
            raise ValueError("every scoped delta result must pass before it can replace the base")
        for result in delta_results:
            ordered_results[positions[result.case_id]] = result
            replaced.append(result.case_id)
        lineage.append(
            {
                "role": "scoped_delta",
                "candidate": delta.get("candidate"),
                "generated_at": delta.get("generated_at"),
                "case_ids": [result.case_id for result in delta_results],
                "summary": delta.get("summary"),
                "gate_checks": delta.get("gate_checks"),
            }
        )
    summary = summarize_agent_eval(ordered_results)
    unauthorized = sum(
        not check.passed
        for result in ordered_results
        for check in result.checks
        if check.name == "no_unconfirmed_write"
    )
    thresholds = release_thresholds()
    gate_checks = {
        "task_success_rate": summary["task_success_rate"]
        >= thresholds["minimum_task_success_rate"],
        "hard_rule_pass_rate": summary["hard_rule_pass_rate"]
        >= thresholds["minimum_hard_rule_pass_rate"],
        "p95_latency": summary["p95_latency_ms"] <= thresholds["maximum_p95_latency_ms"],
        "unauthorized_actions": unauthorized <= thresholds["maximum_unauthorized_action_count"],
    }
    merged = dict(base)
    merged.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "gate": "agent-eval-live-full-scoped-delta",
            "candidate": candidate,
            "status": "passed" if all(gate_checks.values()) else "failed",
            "summary": summary,
            "gate_checks": gate_checks,
            "thresholds": thresholds,
            "results": [result.model_dump(mode="json") for result in ordered_results],
            "verification_lineage": lineage,
            "replaced_case_ids": sorted(set(replaced)),
        }
    )
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--delta", type=Path, action="append", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    deltas = [json.loads(path.read_text(encoding="utf-8")) for path in args.delta]
    report = merge_reports(base, deltas, candidate=args.candidate)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "summary": report["summary"]}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
