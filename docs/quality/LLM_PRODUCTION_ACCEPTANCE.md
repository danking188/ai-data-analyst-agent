# LLM Production Acceptance

## Result

- Date: 2026-09-17
- Gate: live Agent and evidence-narrative acceptance
- Status: passed for the current small-pilot scope
- Deployment: [DataTrace](https://8.222.221.236.sslip.io/)
- Provider/model: DeepSeek OpenAI-compatible API / `deepseek-flash`
- Structured output: prompt mode; thinking disabled
- Rollback: set `LLM_ENABLED=false` and redeploy; deterministic ingestion, analysis, modeling and
  report generation remain available.

No provider token, account password, session value or signed URL is stored in this report. The
production secret remains only in the root-readable server environment file.

## Live workflow

The disposable production workflow used a 120-row classification dataset and exercised both the
deterministic application and the real provider:

1. Upload, profiling, quality scan and confirmed sklearn modeling succeeded.
2. Ten artifacts and two validator-approved claims were persisted.
3. AI report narrative generation succeeded with strict citation and numeric-token validation.
4. A read-only Agent turn called `project.get_context`, `schema.get`, `semantic.list_metrics` and `quality.list_issues` and
   returned cited findings.
5. A requested classification run produced a plan that stopped at `awaiting_confirmation`.
6. Approval resumed execution through `analysis.draft_spec` and `analysis.run`; both succeeded.
7. The test project was archived.

| Metric | Result | Threshold |
| --- | ---: | ---: |
| Agent turns | 3 / 3 succeeded | 100% for release smoke |
| Tool calls | 6 / 6 succeeded | 100% for release smoke |
| Input tokens | 6,461 | informational |
| Output tokens | 2,459 | informational |
| Average Agent latency | 4.235 s | informational |
| P95 Agent latency | 5.095 s | at most 30 s |
| Narrative job | 5.613 s | at most 120 s |
| Unconfirmed writes | 0 | 0 |

## Browser acceptance

Playwright ran against the public HTTPS deployment in desktop and 390px mobile viewports. A new
user registered, created a private project, uploaded a CSV, opened the Agent and completed a cited
read-only turn. The page showed localized completion state, 100% success, 5,242 Token and 21.5 s
P95 for that isolated project. Responsive navigation passed with zero page errors and zero HTTP 5xx.

## Production controls verified

- Model and tool calls are bounded per turn; daily per-user token quota and per-project concurrency
  limits are active.
- Provider failures are isolated by a persistent circuit breaker.
- Tool access is project-bound; writes require explicit confirmation and are audited.
- Unsupported evidence narratives receive one constrained correction attempt, then degrade to a
  cited deterministic answer.
- Invalid or unconfirmed model plans receive one constrained correction attempt and are rejected if
  still outside the write-tool whitelist.
- The analysis target is deterministically removed from `excluded_columns` before confirmation while
  remaining automatically excluded from model features.
- Model training is performed by the deterministic sklearn worker, not by arbitrary LLM-generated code.
- Provider/model settings and secrets are server-side only; the frontend receives capabilities, not keys.

## Remaining conditions

The LLM portion is operational for the current small audience, but wider traffic still requires
provider spend/latency alerts, a defined monthly budget owner, representative concurrency testing,
data/privacy approval and a rehearsed provider-disable rollback. These are operating conditions, not
missing Agent functionality.
