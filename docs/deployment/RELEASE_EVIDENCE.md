# Release Evidence Record

This file defines the evidence that must be attached to every production release. Local candidate
results are useful preflight evidence, but they do not replace immutable registry digests or the
environment sign-off in `PRODUCTION_READINESS.md`.

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
