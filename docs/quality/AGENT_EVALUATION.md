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

## Latest deployed sample

On 2026-09-16, `qwen3.8-flash-agent-p0-final` passed the stratified eight-case sample against the
public Aliyun deployment. All 8 cases passed, task and hard-rule success were both 100%, no
unauthorized write crossed the confirmation boundary, and P95 latency was 21.827 seconds. The
baseline before the routing, bounded-context, refusal, retry, and deterministic-fallback changes
passed 2 of the same 8 cases. The machine-readable comparison is in `AGENT_EVAL_LIVE.json`.

This is canary evidence, not the full 50-case release gate. Before broadening traffic, provision
dedicated immutable time-series, dirty-data, and prompt-injection dataset profiles and run `--full`;
the current sample used fixed classification and regression runs plus non-sensitive adversarial
questions.

## Diagnostic trace

Each `llm_runs.context_manifest_json` now records the selected intent, model call request IDs and
usage, state transitions, evidence validation result, policy decision, and final outcome. Failures
also include a stable category such as `provider`, `plan`, `tool_selection`,
`data_version_conflict`, or `evidence_validation`. Tool arguments and results remain in
`llm_tool_calls`, so a run can be reconstructed without putting raw datasets into the prompt or
trace.
