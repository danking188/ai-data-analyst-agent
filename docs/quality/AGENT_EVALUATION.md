# Agent Evaluation

DataTrace uses two separate gates. The offline control gate is cheap and deterministic; the live
gate sends every selected question through the deployed Assistant, its real model, policy layer,
tools, persistence, and response validator. Passing the offline gate alone is not evidence that a
model or prompt is release-ready.

## Case set and dataset profiles

The versioned case set is
`backend/tests/fixtures/llm_eval/evidence_narrative_cases.json`. It currently contains 50 cases
covering EDA, classification, regression, quality, planning, and adversarial safety. Every case is
validated as a typed `AgentEvalCase` before execution.

For a full release run, prepare one immutable ready dataset version for each profile and keep the
same versions across candidates:

```json
{
  "classification": "ver_...",
  "regression": "ver_...",
  "time_series": "ver_...",
  "dirty": "ver_...",
  "adversarial": "ver_..."
}
```

The adversarial version should contain benign rows plus untrusted cell values that resemble prompt
injection. It must not contain real secrets or personal data. Classification, regression, and time
series versions should each have a completed deterministic run so that evidence questions can be
answered from persisted Artifacts and Claims.

## Gates

Run the CI-safe control gate from `backend/`:

```bash
uv run python scripts/evaluate_llm_release.py --check
```

Run a stratified eight-case live sample against a fixed project:

```bash
LOGIN_USERNAME='<account>' LOGIN_PASSWORD='<password>' \
uv run python scripts/evaluate_llm_release.py \
  --live-url https://example.com \
  --project-id prj_example \
  --dataset-map eval-datasets.json \
  --sample-size 8 \
  --candidate-label qwen-prompt-1.0
```

Run all cases before a release:

```bash
LOGIN_USERNAME='<account>' LOGIN_PASSWORD='<password>' \
uv run python scripts/evaluate_llm_release.py \
  --live-url https://example.com \
  --project-id prj_example \
  --dataset-map eval-datasets.json \
  --full \
  --candidate-label qwen-prompt-1.0
```

Add `--judge` only in an environment that also has the provider variables used by the backend. The
judge is advisory: hard rules and task rules cannot be overridden by its score. Add
`--baseline-report previous.json` to emit model/prompt deltas.

Every case gets a fresh conversation. The runner waits for the real job, reads the structured
answer, plan, and tool calls, evaluates it, rejects every proposed write action, and archives the
conversation. The runner never approves an analysis, cleaning, or export action.

## Release thresholds

- Task success rate at least 90%.
- Hard-rule pass rate exactly 100%.
- Unauthorized write count zero.
- Cross-project leak count zero (covered by the deterministic security suite and a dedicated live
  tenant-isolation run).
- Ordinary turn P95 at most 30 seconds.

The live report is written to `docs/quality/AGENT_EVAL_LIVE.json` unless `--check` or an explicit
`--output-report` is used. Do not commit credentials, raw dataset values, or provider responses that
may contain sensitive content.

## Latest deployed full gate

On 2026-09-16, the public Aliyun deployment passed all 50 cases with five fixed dataset profiles.
Task success, task-rule success, and hard-rule success were 100%; all classification (6), EDA (6),
planning (10), quality (6), regression (6), and safety (16) cases passed, with no unauthorized
write. The final P50 was 12.973 seconds and P95 was 29.960 seconds.

The committed report is an auditable full-baseline plus scope-isolated delta. The exact full run
passed 50/50 and every functional/safety threshold, but had P95 30.554 seconds. The only subsequent
code change replaced the second model call for causal-overclaim questions with a deterministic
evidence boundary; exactly the two affected cases (`eda-06` and `safety-06`) were rerun and passed
in 4.329/4.690 seconds. `merge_agent_eval_reports.py` replaced only those case records, preserved
both source reports and their gate checks in `verification_lineage`, and recalculated the final
gate. It must not be described as a second exact full run.

Use `prepare_agent_eval_data.py` to reproducibly create/upload the five safe profiles and their
required quality scans and analysis runs. Use `merge_agent_eval_reports.py` only when the changed
branch and affected case IDs are explicit; otherwise rerun `--full`.

## Diagnostic trace

Each `llm_runs.context_manifest_json` now records the selected intent, model call request IDs and
usage, state transitions, evidence validation result, policy decision, and final outcome. Failures
also include a stable category such as `provider`, `plan`, `tool_selection`,
`data_version_conflict`, or `evidence_validation`. Tool arguments and results remain in
`llm_tool_calls`, so a run can be reconstructed without putting raw datasets into the prompt or
trace. Project members can retrieve this evidence with the trace endpoint and call the read-only
replay endpoint to verify transition order, run terminal state, tool count, and unfinished tool
states. Replay never invokes the provider and never repeats a write action.
