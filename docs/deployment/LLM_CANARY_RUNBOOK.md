# LLM Canary Runbook

This runbook releases the DataTrace Assistant without weakening the deterministic upload,
quality, cleaning, analysis, modeling, evidence, and export paths.

## Preconditions

1. Run `backend/scripts/evaluate_llm_release.py`; `docs/quality/LLM_RELEASE_GATE.json` must report
   `status=passed` and 50 or more cases.
2. Complete backend Ruff, mypy, pytest, frontend typecheck, Vitest, build, and OpenAPI validation.
3. Confirm PostgreSQL and S3 readiness at `GET /api/v1/health/ready`.
4. Store the provider key only in ModelScope secret management.

## Canary Secrets

```text
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_API_BASE=https://provider.example/v1
LLM_API_KEY=<secret>
LLM_MODEL=<exact-model-id>
LLM_STRUCTURED_OUTPUT_MODE=json_schema
LLM_MAX_CALLS_PER_TURN=4
LLM_MAX_TOOL_CALLS_PER_TURN=8
LLM_DAILY_TOKEN_BUDGET_PER_USER=200000
LLM_MAX_CONCURRENT_TURNS_PER_PROJECT=2
LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
LLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS=60
LLM_RETENTION_DAYS=30
LLM_ARCHIVE_INACTIVE_DAYS=90
LLM_CANARY_SUBJECTS=<authenticated-subject-id>
```

The ModelScope Studio access token and the inference provider key are different credentials unless
the selected inference endpoint explicitly accepts the Studio token.

## Smoke Sequence

1. Register or sign in with the allowlisted account.
2. Upload a real CSV and wait for ingestion, schema inference, and quality scan.
3. Ask a read-only quality question; verify every numeric finding opens a real Claim or Artifact.
4. Request a classification or regression analysis; edit the proposed AnalysisSpec.
5. Reject once and confirm that no resource was created, then generate a fresh plan and approve it.
6. Wait for the real Analysis Worker and inspect candidate metrics, model artifact, and limitations.
7. Request a cleaning proposal, inspect its real preview, approve it, and verify a new dataset
   version is created without mutating the source version.
8. Check `GET /api/v1/projects/{project_id}/assistant/metrics?window_days=7` for Turn, Token,
   latency, tool success, failure, and rejection counts.
9. Restart the Studio and confirm the account, conversation, dataset, run, and artifact persist.

## Acceptance

- Standard canary questions succeed at least 90% of the time.
- Numeric finding evidence coverage is 100%.
- Cross-project leaks and unconfirmed writes remain zero.
- Ordinary Turn P95 is at most 30 seconds, excluding confirmed model training.
- A provider failure degrades only LLM routes; health, data, analysis, and reports stay usable.

## Rollback

1. Set `LLM_ENABLED=false` and redeploy the Studio.
2. Leave PostgreSQL migrations and audit records intact.
3. Stop or cancel queued `assistant_turn` jobs; do not downgrade the database during an incident.
4. Verify login, project list, dataset preview, quality, deterministic analysis, and export.
