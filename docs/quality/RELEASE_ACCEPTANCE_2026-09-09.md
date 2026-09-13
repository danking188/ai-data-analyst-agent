# DataTrace Release Acceptance Report — 2026-09-09

Historical snapshot: this report describes the ModelScope/local candidate on 2026-09-09.
The current public deployment is [DataTrace on Aliyun](https://8.222.221.236.sslip.io/), with a
`CONDITIONAL GO` small-pilot decision recorded in [the latest target acceptance](./SMALL_TRAFFIC_ACCEPTANCE.md).
The historical `NO-GO` below is not the current Aliyun availability status.

## Decision

**Repository/workspace candidate: PASS. Production release: NO-GO pending external evidence.**

The current workspace has enough functional, regression, recovery and local capacity evidence to
be deployed as an immutable release candidate. It is not yet authorized for public traffic because
the ModelScope target is access-token protected, the current workspace is not committed/published,
and target infrastructure/security/operational approvals are incomplete.

## Candidate identity

| Field | Value |
| --- | --- |
| Base commit | `82eb7f8ea4268321c920c0c097547f9ccbbe7d60` |
| Source state | Base commit plus reviewed local release-hardening/documentation changes |
| Pilot image | `datatrace-pilot:small-traffic-rc` |
| Local image identifier | `sha256:4d0b4b18de2a75f9761291cfa26ed5fa31e013c0e1c58d3e7da857df14950021` |
| Target | ModelScope Studio `Ascano/ai-data-analyst-agent` |

The source and image identifiers above are not immutable production release identifiers. A commit
SHA and signed registry digest must replace them before release approval.

## Verification summary

| Area | Result | Evidence |
| --- | --- | --- |
| Backend static quality | PASS | Ruff and strict Mypy passed |
| Backend regression | PASS | 151 tests passed; 82.78% coverage; two non-blocking dependency/runtime warnings |
| Frontend regression | PASS | 26 tests, TypeScript check and Vite production build passed |
| API contract | PASS | 50 paths, 63 operations and 398 references validated |
| LLM offline gate | PASS | 50 L4 evaluation cases passed |
| Dependency audit | PASS | `pip-audit` and production `pnpm audit` reported no known vulnerabilities |
| Configuration/tooling | PASS | Compose rendering, workflow YAML, shell syntax, Python compilation and repository hygiene passed |
| Container auth/smoke | PASS | Missing explicit production auth failed closed; login, readiness, capabilities and security headers passed after valid configuration |
| Representative workflow | PASS | Post-hardening run: 120-row CSV through ingestion, quality, confirmed analysis, 10 artifacts, 2 validated claims, 4,159-byte HTML report and protected download; disposable project archived |
| Small read traffic | PASS (local) | Final post-hardening run: 500 requests, concurrency 8, 0 errors, P95 9.738 ms and throughput 1,209.067 requests/s |
| PostgreSQL recovery | PASS (local) | PostgreSQL 16 migrated to `20260713_0002`; checksum-verified backup restored 28 public tables into an isolated database at the same head |
| Current image registry scan/signing | PENDING | Requires immutable CI SHA, Trivy gate, registry digest, SBOM/provenance and Sigstore evidence |
| Target deployment acceptance | BLOCKED | Studio page returns 200, but the app origin returns 403 and the API origin returns 401 without a valid ModelScope token |

The target was re-probed on 2026-09-09. The public project page was reachable, while
`https://ascano-ai-data-analyst-agent.ms.show/` returned HTTP 403 and directed clients to the API
origin. `https://studio-ascano-ai-data-analyst-agent.api-inference.modelscope.net/` returned HTTP
401 with an authentication-required response. This proves platform presence, not application
readiness or audience access.

## Capacity observation

The final post-hardening local pilot run served the required 500 read requests with zero failures.
Mean/P50/P95/P99/max latencies were 6.334/6.219/9.738/11.172/13.685 ms. Sampled runtime
consumption across the acceptance runs was approximately 376–527 MiB memory, 44–65 PIDs and
0.40–0.45% CPU. This demonstrates ample headroom for the
defined small read-traffic profile on the local host; it does not predict target-platform capacity
without an equivalent target run.

The final representative workflow completed ingestion, quality, analysis and report generation in
0.540/1.027/3.553/1.027 seconds. Its same-origin authenticated flow remained functional after the
smoke clients were hardened to strip platform/session credentials from cross-origin redirects and
external signed download URLs.

## Recovery evidence

The rehearsal used PostgreSQL 16, applied every Alembic migration through `20260713_0002`, created
a 91,453-byte custom-format dump, verified SHA-256
`9d6ccc6a89382cca62d78fce7e00621c28517095b69870fca1fda187e7ed1013`, and restored into a
separate database. The restored database reported the same migration head and 28 public tables.
Temporary backup material and the rehearsal container were removed after evidence capture.

## Required production closure

Production can change from `NO-GO` to `GO` only after all of the following are attached to the same
immutable source SHA:

1. CI and security workflows pass; the deployed digest is scanned, signed and accompanied by
   verified SBOM/provenance.
2. ModelScope production secrets are configured without committing credentials, the new revision is
   deployed, and the target HTTPS origin is usable by the intended audience.
3. Deployment smoke, representative workflow and the 500-request/concurrency-8 probe pass against
   the target origin.
4. Target PostgreSQL TLS/PITR and S3 encryption/versioning/object restore are verified.
5. WAF/rate limiting, centralized logs, metrics and alert delivery are exercised with a named
   receiver; rollback is rehearsed against an immutable previous digest.
6. Release Manager, Security, DBA/SRE, Product and required privacy/legal owners sign the production
   readiness checklist.

No passwords, cookies, API keys, signed URLs or user data are included in this report.
