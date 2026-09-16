# Release Evidence Record

This file defines the evidence that must be attached to every production release. Local candidate
results are useful preflight evidence, but they do not replace immutable registry digests or the
environment sign-off in `PRODUCTION_READINESS.md`.

## Aliyun Agent release and source sync (2026-09-15)

Public website: [DataTrace](https://8.222.221.236.sslip.io/).
Public self-registration and account isolation remain enabled. A new account completed automatic
login, private-project isolation, logout/relogin, upload, quality scan, real model training and HTML
report download. The workflow produced 10 artifacts and 2 validated claims.

The Alibaba Cloud Model Studio OpenAI-compatible provider is enabled with `qwen3.8-flash`. The live
Agent acceptance completed an AI evidence narrative, a cited read-only turn and a new-analysis turn
that stopped before confirmation, then ran its approved AnalysisSpec and model job. All 3 Agent turns
and all 5 tool calls succeeded. Defensive correction now covers evidence-number formatting, invalid
plans and the model placing its target in `excluded_columns` without weakening deterministic validators.

Local checks passed 154 backend and 33 frontend tests, 83% backend coverage, Ruff, strict Mypy,
TypeScript, OpenAPI and the production build. The server-side 500-request/concurrency-8 read probe
had zero failures, 50.612 RPS and P95 228.934 ms. Playwright passed desktop and 390px registration,
project creation, upload, real Agent read turn and responsive navigation with no page error or HTTP 5xx.
The deployed source, Aliyun scripts and documentation are synchronized in the current GitHub update;
the commit containing this file is the source reference. This does not replace a signed image digest,
fresh remote CI/security result or the broader environment sign-off. Detailed evidence and operational
conditions are in [small-traffic acceptance](../quality/SMALL_TRAFFIC_ACCEPTANCE.md).

## Agent P0 evaluation hardening (2026-09-16)

The public Aliyun deployment was updated with prompt routing version `assistant.intent@1.1.0`,
explicit policy refusal, bounded evidence context, one low-temperature retry for malformed intent
JSON, deterministic evidence fallback, stable failure categories, and replayable model/tool traces.
The deployment keeps all write tools behind explicit confirmation.

The real-provider stratified sample improved from 2/8 to 8/8 on the same case selection. Task and
hard-rule pass rates were 100%, P95 was 21.827 seconds, all 17 executed read tools succeeded, the
single proposed write was rejected by the evaluator, and no unauthorized write occurred. The
machine-readable report is [`AGENT_EVAL_LIVE.json`](../quality/AGENT_EVAL_LIVE.json). This evidence
does not replace the required full 50-case run with five dedicated immutable dataset profiles.

## Automated release artifacts

Pushing a `v*` tag, or manually dispatching `Release container images`, first reruns CI and the
security workflow. Only after both pass does it publish backend, frontend and pilot images to
GHCR. Each image is built for `linux/amd64` and `linux/arm64` with:

- an SPDX SBOM and maximum-mode build provenance attached to the OCI image;
- a content digest and immutable source commit;
- a Sigstore keyless signature issued through GitHub OIDC;
- a 90-day JSON evidence artifact containing the image, digest, source SHA/ref and workflow URL.

The release manager must download the three `release-evidence-*` artifacts and retain them with
the deployment record.

## Release sign-off template

| Field | Required value |
| --- | --- |
| Release tag | Immutable `v*` tag |
| Source SHA | Green CI/security commit SHA |
| Backend image | GHCR reference pinned by digest |
| Frontend image | GHCR reference pinned by digest |
| Pilot image | GHCR reference pinned by digest, if used |
| SBOM/provenance | OCI attestations verified for every deployed digest |
| Signature | Sigstore verification result for every deployed digest |
| Migration | Production-like PostgreSQL rehearsal record |
| Smoke | Login, upload, analysis, artifact download and readiness evidence |
| Small traffic | JSON summary for 500 requests at concurrency 8, with ≤1% errors and P95 ≤2s |
| Rollback | Previous known-good image digests and tested rollback command |
| Approval | Release manager, Security, DBA/SRE and Product names/dates |

## Current local candidate preflight

On 2026-08-11, the local `linux/arm64` candidate builds produced attached SBOM/provenance and
passed Docker Scout with zero fixable Critical or High vulnerabilities. Backend and pilot run as
UID 999; frontend Nginx runs as UID 101 on port 8080. The frontend returned HTTP 200 with the
configured CSP and browser security headers. The pilot rejected missing production settings, then
successfully ran migrations, the worker, API and readiness probe with disposable test settings.

These local tags and digests are intentionally not treated as release identifiers. `ENV-109`
remains open until a green immutable CI SHA is published, signed and rehearsed in the target
environment.

### 2026-09-08 workspace candidate

The current workspace (base commit `82eb7f8ea4268321c920c0c097547f9ccbbe7d60` plus the
documented local release-hardening changes) passed the repository gates: Ruff, strict Mypy,
151 backend tests at 82.78% coverage, 26 frontend tests, TypeScript, the frontend production
build, OpenAPI 50-path/63-operation/398-reference validation, the 50-case offline LLM gate,
Compose rendering, shell/Python syntax and repository hygiene. Production dependency audits
reported no known Python or frontend vulnerabilities.

The rebuilt pilot image `datatrace-pilot:small-traffic-rc` has local image identifier
`sha256:4d0b4b18de2a75f9761291cfa26ed5fa31e013c0e1c58d3e7da857df14950021`.
It rejected a missing explicit production auth mode, then passed authenticated deployment smoke,
a disposable upload-to-report workflow, and 500 read requests at concurrency 8 with zero errors
and final post-hardening P95 latency of 9.738 ms (1,209.067 requests/s). Cross-origin redirects
and external signed download URLs are verified not to receive session or platform credentials.
A PostgreSQL 16 rehearsal applied migrations to
`20260713_0002`, verified backup checksum
`9d6ccc6a89382cca62d78fce7e00621c28517095b69870fca1fda187e7ed1013`, and restored 28
public tables into an isolated database at the same migration head.

This image identifier is local and mutable, and the source changes are not yet represented by an
immutable commit. Current-image Trivy/registry scanning, signing, target S3 recovery, target
deployment smoke/load and named environment approvals remain required. Docker Scout was not run
for this workspace candidate because the available invocation could transmit private package/SBOM
metadata to an external service; the release workflow's non-exporting Trivy gate remains the
required scan path.
