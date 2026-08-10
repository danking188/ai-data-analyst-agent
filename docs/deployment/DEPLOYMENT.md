# Production Deployment Guide

The supported production topology is the root `docker-compose.yml`:

- `migrate`: one-shot Alembic release step.
- `backend`: stateless FastAPI processes; no background jobs run in API processes.
- `worker`: isolated database-backed analysis worker with a separate CPU/memory budget.
- `frontend`: immutable Vite build served by Nginx and same-origin API proxy.
- external PostgreSQL and private S3-compatible storage.

The root single-container image remains available for platforms that cannot run multiple
services. It supervises API and worker in one container and is therefore intended only for a
controlled pilot; it does not provide independent scaling or failure isolation.

The single-container pilot is also fail-closed: at runtime it still requires a non-placeholder
`JWT_SECRET`, `LOGIN_PASSWORD`, exact public `TRUSTED_HOSTS`, `CORS_ORIGINS`, and the appropriate
database/storage credentials. The image intentionally does not contain fallback production
credentials. Override `PORT` only when the hosting platform does not use the default `7860`.

## 1. Configure secrets and infrastructure

```bash
cp .env.deploy.example .env.deploy
chmod 600 .env.deploy
```

Replace every example value. In particular:

- use a TLS-required PostgreSQL URL and a database role scoped to this application;
- use a private S3 bucket and scoped object credentials;
- generate a random `JWT_SECRET` of at least 32 bytes;
- store `LOGIN_PASSWORD`, database, S3 and LLM credentials in the platform secret manager;
- set `CORS_ORIGINS` to the exact public HTTPS origin;
- set `TRUSTED_HOSTS` to the public host plus the internal health-check hosts;
- keep `REGISTRATION_ENABLED=false` unless self-service account creation is intentional;
- keep `SESSION_COOKIE_SECURE=true`.

The app refuses to start in production with development authentication, insecure cookies,
wildcard/missing trusted hosts, placeholder credentials, local persistence when external
persistence is required, or insecure S3/LLM endpoints.

TLS must terminate at a managed load balancer/CDN in front of port 8080. Do not expose the
backend container port directly. Allow 105 MiB of transport body overhead while the app enforces
a strict 100 MiB file limit; also configure a WAF
or per-IP login/upload throttle, access logs, and health checks at `/api/v1/health/ready`.

## 2. Run local release gates

```bash
ENV_FILE=.env.deploy ./scripts/production_gate.sh
docker compose --env-file .env.deploy build
```

CI repeats backend lint/type/test/coverage, frontend type/test/build, OpenAPI validation,
Compose rendering, image builds, dependency audits and a high/critical container scan. Every
candidate image is built with an attached SBOM and provenance. Version tags publish signed
multi-architecture images and evidence manifests as described in
[`RELEASE_EVIDENCE.md`](./RELEASE_EVIDENCE.md).

## 3. Deploy

```bash
docker compose --env-file .env.deploy up -d --build
docker compose --env-file .env.deploy ps
```

`backend` and `worker` start only after the `migrate` service exits successfully. The frontend
starts only after backend readiness succeeds. All application images run as non-root users; the
frontend Nginx process listens on container port 8080.

Run an authenticated smoke test against the public HTTPS origin:

```bash
FRONTEND_URL=https://analytics.example.com \
BACKEND_URL=https://analytics.example.com/api/v1 \
LOGIN_USERNAME=analyst \
LOGIN_PASSWORD='read-from-secret-manager' \
./scripts/deploy_smoke.sh
```

Never pass real secrets in shared shell history or CI logs; inject them through the deployment
platform.

## 4. Backups and restore drill

Create an encrypted backup target outside the application host, then run:

```bash
DATABASE_URL='secret-managed-url' BACKUP_DIR=/explicit/secure/backup/path \
  ./scripts/backup_postgres.sh

S3_BUCKET=private-bucket S3_ENDPOINT_URL=https://objects.example.com \
  ./scripts/verify_s3_versioning.sh
```

Quarterly, restore the newest archive into an isolated database and run the smoke test. The
restore script is intentionally destructive and requires an exact confirmation value:

```bash
DATABASE_URL='isolated-restore-database-url' \
BACKUP_FILE=/explicit/secure/backup/path/datatrace-YYYYMMDDTHHMMSSZ.dump \
CONFIRM_RESTORE=RESTORE_DATATRACE_DATABASE \
  ./scripts/restore_postgres.sh
```

Use provider-managed point-in-time recovery in addition to dumps. Set bucket versioning,
retention and lifecycle policies at the object-storage provider; the application cannot enforce
provider-side durability.

## 5. Monitoring and rollback

The API emits JSON production logs containing timestamp, level, request ID, method, path,
status and duration, without request bodies or credentials. Collect stdout centrally and alert on:

- readiness failures for two consecutive checks;
- elevated HTTP 5xx or authentication failures;
- worker restarts, stale leases or queued jobs older than the agreed SLO;
- PostgreSQL saturation/replication lag and S3 errors;
- memory pressure near the API or worker container limit;
- LLM circuit-breaker openings and token-budget exhaustion when LLM is enabled.

Rollback by restoring the previous immutable `IMAGE_TAG`; do not downgrade the database until a
migration-specific rollback has been rehearsed. Disable LLM immediately with `LLM_ENABLED=false`
if provider behavior is unsafe. See `LLM_CANARY_RUNBOOK.md` for staged enablement.

The complete owner/sign-off checklist is in
[`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md).
