# Production Readiness and Sign-off

Repository work is considered release-ready only when CI is green and every environment-owned
item below has a named owner and dated evidence. A code change cannot prove DNS, TLS, backups,
alerts, legal approval or third-party capacity.

## Implemented in the repository

- Production-only JWT sessions; no development token is embedded in the frontend image.
- Secure, HttpOnly, SameSite session cookie plus double-submit CSRF protection on cookie-authenticated writes.
- Production startup validation for secrets, HTTPS endpoints, secure cookies, trusted hosts and external persistence.
- Production docs disabled, strict CORS, Host validation, CSP/HSTS and standard browser security headers.
- Same-origin Nginx proxy with a 100 MiB edge limit; application streaming upload size/type/signature checks.
- API/migration/worker service separation, non-root backend/frontend/pilot images, no-new-privileges, PID/CPU/memory limits.
- PostgreSQL metadata and private S3-compatible immutable files with compensation on ingestion commit failure.
- Readiness checks for database and object storage; structured request logs and request IDs.
- Reproducible frontend and backend lockfiles; CI, dependency audit, container scan and Dependabot.
- Tag-gated multi-architecture release images with attached SBOM/provenance, immutable evidence manifests and Sigstore keyless signatures.
- Functional project/version selection, cursor preview pagination, version comparison and capability-driven UI.
- Database dump/restore verification scripts and S3 versioning verification.

## Environment sign-off required before traffic

| Area | Required evidence | Owner | Status |
| --- | --- | --- | --- |
| DNS/TLS | Public hostname, valid certificate, HTTP→HTTPS redirect, TLS scan | Platform | Open |
| Edge security | Backend not public, 100 MiB limit, WAF/per-IP throttles, DDoS controls | Platform/Security | Open |
| Secrets | Secret-manager references, rotation procedure, no examples in runtime | Security | Open |
| PostgreSQL | TLS, least-privilege role, PITR, retention, connection/capacity test | DBA | Open |
| Object storage | Private bucket, scoped role, encryption, versioning/lifecycle, restore proof | Platform | Open |
| Observability | Central logs, dashboards, paging routes, synthetic ready/login/upload probe | SRE | Open |
| Reliability | Load/soak test with representative maximum files and worker concurrency | QA/SRE | Open |
| Recovery | Fresh PostgreSQL restore plus object retrieval in isolated environment | DBA/QA | Open |
| Privacy | Data classification, retention/deletion policy, privacy notice/DPA, residency | Legal/Security | Open |
| Accounts | Decide bootstrap/invite/SSO model; registration remains disabled by default | Product/Security | Open |
| LLM | Offline gate, provider DPA, masked-data policy, named-subject canary and rollback | AI/Security | Open |
| Release | CI SHA, signed image digests/SBOM/provenance, migration rehearsal, smoke evidence | Release manager | Open |

## Go/no-go gates

No-go if any of these is true:

- CI/security workflow is red or an unaccepted critical/high vulnerability exists;
- readiness fails or migrations have not been rehearsed on a production-like PostgreSQL copy;
- restore proof is older than the agreed drill interval;
- backend is directly internet reachable or TLS/secure-cookie behavior is not verified;
- maximum representative upload causes OOM, API starvation or unbounded queue growth;
- alerts have no tested receiver or rollback image/digest is unavailable;
- legal/privacy approval is missing for the intended data or LLM provider.

After deployment, run the smoke script, upload a non-sensitive representative file, produce and
download an artifact, inspect logs by request ID, then observe the canary window before widening
traffic.

Use [`RELEASE_EVIDENCE.md`](./RELEASE_EVIDENCE.md) as the release-manager evidence template.
