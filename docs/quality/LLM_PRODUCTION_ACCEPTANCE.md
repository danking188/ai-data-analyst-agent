# LLM Production Acceptance

## Result

- Date: 2026-07-13
- Gate: L4 live canary
- Status: passed
- Deployment: `https://ascano-ai-data-analyst-agent.ms.show`
- Studio: `https://www.modelscope.cn/studios/Ascano/ai-data-analyst-agent`
- Validated revision: `d8cea14`
- Provider/model: ModelScope OpenAI-compatible inference / `Qwen/Qwen3.5-35B-A3B`
- Rollback: set `LLM_ENABLED=false` and redeploy; deterministic data workflows remain available.

No provider token, database credential, object-storage credential, account password, or session value
is stored in this report.

## Infrastructure

The public readiness endpoint returned `ready` with:

- Database backend: PostgreSQL, status `ok`
- Object storage backend: S3, status `ok`
- Authentication, registration, project membership, persistence, and canary allowlisting enabled

The deployment retained the canary account, projects, dataset versions, conversations, and audit data
across rebuilds.

## Read-Only Assistant Canary

An isolated project uploaded and parsed a 20-row, 5-column CSV, then completed a real quality scan.
Five standard schema and quality questions were executed sequentially with the production provider.

| Metric | Result | Threshold |
|---|---:|---:|
| Successful turns | 5 / 5 (100%) | at least 90% |
| Average LLM run latency | 12.190 s | informational |
| P95 LLM run latency | 13.336 s | at most 30 s |
| Tool calls succeeded | 15 / 15 (100%) | 100% for canary |
| Findings with citations | 25 / 25 (100%) | 100% |
| Failed or unconfirmed writes | 0 | 0 |

All five answers used the deterministic evidence fallback after the model narrative failed strict source
validation. The user still received real Schema/quality results with valid source IDs, but improving the
provider-specific citation prompt remains a post-L4 quality task. The validator must not be weakened to
reduce this fallback rate.

## Controlled Modeling Canary

The user requested a binary classification plan with `churned` as the target, `customer_id` excluded,
stratified splitting, and `roc_auc`, `f1`, `precision`, and `recall` metrics.

1. The first valid plan stopped at `awaiting_confirmation`.
2. Rejecting it produced zero AnalysisSpecs and zero Runs.
3. A fresh plan was generated and both explicit steps were approved.
4. The confirmed execution created one confirmed AnalysisSpec and one succeeded real Run.
5. The Run produced 10 ready Artifacts: EDA metrics/table/charts, target diagnostics, statistical tests,
   candidate comparison, holdout metrics, model card, limitations, and a serialized sklearn Pipeline.
6. Candidate selection compared Dummy, logistic regression, and histogram gradient boosting using
   training-only cross-validation. The holdout partition was used once after selection.

The tiny canary dataset had only 20 rows and a 4-row holdout. Its perfect holdout metrics prove pipeline
execution only; they are not evidence of production generalization, calibration, or business value.

## Production Controls Verified

- Model calls and tool calls are bounded per turn.
- Daily per-user token quota and per-project concurrency limits are active.
- Provider failures are isolated by a persistent circuit breaker.
- Tool access is project-bound; writes require explicit confirmation and are audited.
- Unsupported model narratives receive one correction attempt, then degrade to cited deterministic output.
- ModelScope uses prompt-structured output because its endpoint did not return usable `json_schema`
  choices during compatibility probing.
- `LLM_ENABLE_THINKING=false` is enabled only through the optional provider-specific setting; the same
  Qwen probe returned valid JSON in 0.54 seconds and 27 tokens.

## Follow-Up Improvements

These items do not block Gate L4 but should be prioritized for broader production use:

1. Reduce deterministic narrative fallback from 100% to below 10% with provider-specific citation examples
   and schema-constrained source selection, while preserving the strict validator.
2. Benchmark planning latency and concurrency on a provider tier with an explicit SLA before opening the
   canary allowlist broadly.
3. Validate model quality on representative datasets with larger untouched holdouts, temporal or grouped
   splits where appropriate, calibration checks, and domain-reviewed success criteria.
4. Archive the isolated acceptance projects after the team no longer needs their evidence for inspection.
