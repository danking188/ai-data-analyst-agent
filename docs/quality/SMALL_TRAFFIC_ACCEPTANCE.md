# Small-Traffic Production Acceptance

This runbook defines the minimum repeatable evidence for opening DataTrace to a small production
audience. It supplements, but does not replace, the infrastructure and compliance sign-off in
`docs/deployment/PRODUCTION_READINESS.md`.

## Latest target acceptance (2026-09-17)

Public website: [DataTrace](https://8.222.221.236.sslip.io/).
The public readiness endpoint returned `ready`, database `ok` (SQLite), object storage `ok`
(local), and registration remained enabled. A registered user completed session, isolation,
logout/relogin and the upload-to-report workflow. A real DeepSeek Agent completed cited read tools,
plan/confirmation and controlled model execution. The 50-case offline Agent gate, project-bound
read-only trace replay, counterfactual trace comparison, structured memory and version-bound semantic
metrics passed. The full local regression passed 201 backend and 37 frontend tests, 83.32% backend
coverage, type checks, OpenAPI validation and the production frontend build.

## Acceptance profile

Run the read-only probe against the exact public HTTPS origin after deployment:

```bash
LOGIN_USERNAME='read-from-secret-manager' \
LOGIN_PASSWORD='read-from-secret-manager' \
python3 scripts/small_traffic_test.py \
  --base-url https://analytics.example.com \
  --requests 500 \
  --concurrency 8 \
  --require-authenticated \
  --max-error-rate 0.01 \
  --max-p95-ms 2000 \
  --min-throughput-rps 2
```

The probe performs only health, readiness, session and capability reads after one login. It never
uploads data, starts jobs or changes application state beyond creating the login session. For a
private hosting platform, pass the name of the environment variable containing its outer bearer
token with `--platform-token-env`; the token value is never printed.

## Required evidence

| Check | Acceptance criterion | Current evidence |
| --- | --- | --- |
| Functional regression | Backend/frontend/contract gates pass | 201 backend and 37 frontend tests, 83.32% coverage, type checks, OpenAPI and production build passed |
| Production image | Non-root image starts and readiness passes | Aliyun single-container image passed startup, readiness and reboot recovery |
| Authenticated smoke | Registration, login, session, capabilities and frontend proxy pass | Rerun on the public Aliyun HTTPS origin on 2026-09-15; reboot recovery remains verified from 2026-09-11 |
| Account isolation | One account cannot list another account's project | Registered account project stayed hidden from the bootstrap administrator before and after reboot |
| Small read traffic | 500 requests, concurrency 8, error rate ≤1%, P95 ≤2s | Post-deploy sample: server-side 200/concurrency 8 at 56.061 RPS and 220.333 ms P95; workstation 100/concurrency 5 at 3.650 RPS and 1,465.980 ms P95; both had 0 failures |
| Representative workflow | Upload, quality scan, analysis, evidence and download pass | Registered account passed: 10 artifacts, 2 validated claims and a 4,159-byte report; real Agent plan/confirm/execute also passed |
| Browser workflow | Desktop/mobile registration and primary Agent interaction pass | Playwright passed registration, project creation, upload, Agent read turn and 390px navigation; 0 page errors, 0 HTTP 5xx |
| Recovery | A current local backup exists and services recover after reboot | SQLite online backup and file archive passed; off-server recovery remains pending |
| Observability | One-minute readiness probe and restart after 3 consecutive failures | Active systemd timer; external alert receiver remains pending |
| Security edge | TLS, backend isolation and security headers verified | Passed with Let's Encrypt TLS, Caddy-only public ports, UFW, Fail2ban and key-only SSH |

## Aliyun lightweight production result (updated 2026-09-17)

The small-traffic deployment is live at [DataTrace](https://8.222.221.236.sslip.io/) on the Singapore
lightweight instance `Ubuntu-qpqv` (Ubuntu 24.04, 2 vCPU, 2 GB plan, 40 GB disk). This is a
single-host pilot topology using Caddy, a non-root application container, persistent local storage
and SQLite.

| Item | Result |
| --- | --- |
| Public readiness | Database `ok` (SQLite) and object storage `ok` (local) |
| Authenticated smoke | Login, session, capabilities, frontend, proxy and required security headers passed |
| Registration integration | Public registration, automatic session, private project creation, logout/relogin and post-reboot login all passed |
| Server-side read traffic | 2026-09-17: 500 requests at concurrency 8; 0 failures; 54.740 requests/s |
| Server-side latency | Mean 144.669 ms; P50 140.503 ms; P95 211.184 ms; P99 251.662 ms; max 314.744 ms |
| Cross-border observation | 2026-09-17 workstation direct run: 498/500 succeeded (0.4% errors), 6.484 requests/s, P95 3,022.280 ms; two TLS handshakes timed out. It meets the ≤1% error criterion but not the 2-second end-to-end latency criterion; server-side results isolate the application capacity from this route variability without claiming the route is universally fast |
| Representative workflow | Registered account: ingestion 0.552 s; quality 1.079 s; analysis 2.758 s; report 1.082 s; test project archived |
| Real Agent workflow | 3/3 turns and 6/6 tools succeeded; cited read tools, confirmation boundary and confirmed model run passed; Agent P95 5.095 s in the 2026-09-17 API workflow |
| High-value Agent additions | Structured memory `structured-memory@1.0.0`, active semantic metric create/list, and evidence-auditor trace comparison with valid citations passed on the public deployment |
| Browser workflow | Historical desktop/390px full flow passed; 2026-09-17 Chrome verified login rendering and the Agent “回放校验” drawer with four successful consistency checks. The only remaining console network error was the expected pre-login `/auth/session` 401 |
| Resource observation | Application about 610 MiB and Caddy about 12 MiB after tests; 2 GB swap configured and unused; 29 GB disk free |
| Recovery | Full server reboot completed after registration; both containers returned automatically and the new account/project remained available |
| Backup | Validated SQLite snapshot, non-database file archive and SHA-256 manifest; daily timer with 14-day local retention |
| Operations | One-minute readiness timer, restart after 3 consecutive failures, bounded Docker logs, UFW and Fail2ban active |
| Decision | `CONDITIONAL GO` for a small pilot audience |

The remaining conditions are operational rather than application blockers: enable renewal before
the current subscription expires, add an external alert receiver, copy daily backups off the
server, and replace the temporary `sslip.io` hostname with an owned domain for long-term use. The
Agent uses DeepSeek's OpenAI-compatible endpoint with `deepseek-flash`; provider
quota, spend and latency must be monitored before widening traffic.

## Local candidate result (2026-09-08)

This result validates the current workspace and single-container pilot image only. It is not a
substitute for running the same checks against an immutable target deployment.

| Item | Result |
| --- | --- |
| Candidate image | `datatrace-pilot:small-traffic-rc` (`sha256:4d0b4b18de2a75f9761291cfa26ed5fa31e013c0e1c58d3e7da857df14950021`) |
| Fail-closed auth | Startup without an explicit production `AUTH_MODE` was rejected as required |
| Deployment smoke | Login, authenticated session, capabilities, readiness and required security headers passed |
| Read traffic | Final post-hardening run: 500 requests at concurrency 8; 0 failures; 0% error rate; 1,209.067 requests/s |
| Latency | Mean 6.334 ms; P50 6.219 ms; P95 9.738 ms; P99 11.172 ms; max 13.685 ms |
| Representative workflow | 120-row CSV; upload, quality scan, confirmed analysis, 10 artifacts, 2 validated claims, HTML report and download passed |
| Workflow timing | Final post-hardening run: ingestion 0.540 s; quality 1.027 s; analysis 3.553 s; report 1.027 s |
| Runtime observation | Approximately 376–527 MiB memory, 44–65 PIDs and 0.40–0.45% CPU during sampled observations |
| PostgreSQL recovery | All Alembic migrations reached `20260713_0002`; backup checksum verified; isolated restore produced 28 public tables at the same head |

The local read probe therefore met the numerical small-traffic threshold with substantial
headroom. This historical local result did not by itself authorize production; the current target
decision and remaining conditions are recorded in the Aliyun section above.

## Test report template

Record the following with the release evidence:

- UTC timestamp, public origin and source SHA;
- hosting profile and resource allocation;
- request count, concurrency, error rate, throughput, P50/P95/P99/max latency;
- status counts and up to five sanitized sample errors;
- representative workflow dataset size and job durations;
- CPU, memory and queue-depth observations during the run;
- alert receiver, rollback digest and named approver;
- final `GO`, `CONDITIONAL GO` or `NO-GO` decision.

Do not record passwords, cookies, API keys, signed URLs or raw user data in the report.

Run the disposable representative workflow with a dedicated smoke account. The generated project
is archived after success or failure unless `--keep-project` is explicitly supplied:

```bash
LOGIN_USERNAME='read-from-secret-manager' \
LOGIN_PASSWORD='read-from-secret-manager' \
python3 scripts/production_workflow_smoke.py \
  --base-url https://analytics.example.com
```
