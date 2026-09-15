# Production Deployment Guide

## Current public deployment (2026-09-15)

[DataTrace](https://8.222.221.236.sslip.io/) is running on an Aliyun Singapore lightweight
server. Self-registration and the Qwen-backed Agent are enabled. The current pilot uses Caddy, a single application container,
SQLite and persistent host files; it does not use the separated PostgreSQL/S3 topology below.
Public readiness, registration, upload-to-report, real Agent plan/confirm/execute, desktop/mobile
browser flow and 500-request acceptance were rerun on 2026-09-15. Reboot recovery was completed
on 2026-09-11.
See [target evidence](../quality/SMALL_TRAFFIC_ACCEPTANCE.md) and
[Aliyun operations](./ALIYUN_LIGHTWEIGHT.md). The pilot decision is `CONDITIONAL GO`;
off-host backups, external alert delivery, an owned domain and renewal arrangements remain pending.

## Separated production topology

The supported production topology is the root `docker-compose.yml`:

- `migrate`: one-shot Alembic release step.
- `backend`: stateless FastAPI processes; no background jobs run in API processes.
- `worker`: isolated database-backed analysis worker with a separate CPU/memory budget.
- `frontend`: immutable Vite build served by Nginx and same-origin API proxy.
- external PostgreSQL and private S3-compatible storage.

The root single-container image remains available for platforms that cannot run multiple
services. It supervises API and worker in one container and is therefore intended only for a
controlled pilot; it does not provide independent scaling or failure isolation.

For a lowest-cost, single-project deployment on an Alibaba Cloud Simple Application Server,
use the resource-constrained profile and host bootstrap in
[`ALIYUN_LIGHTWEIGHT.md`](./ALIYUN_LIGHTWEIGHT.md). It is designed for a 2 vCPU / 2 GB small-traffic
pilot with host persistence and automatic HTTPS, not for high availability. Keep off-host backups
and migrate to the separated production topology when uptime or concurrency requirements grow.

For ModelScope friend/beta deployments, keep SQLite and local object files under
`/mnt/workspace/data`, set `REQUIRE_EXTERNAL_PERSISTENCE=false` and `STORAGE_BACKEND=local`, and
use the platform-provided HTTPS endpoint. Set `CSRF_MODE=origin` with `CORS_ORIGINS` equal to that
exact HTTPS origin on proxies that preserve only one application `Set-Cookie` header. The pilot
entrypoint prepares the runtime-mounted workspace and then drops privileges before migrations,
API, or worker code starts. This profile does not require PostgreSQL, S3 or WAF services, but
deleting or renaming the Studio can still remove its persisted workspace.

Set `REGISTRATION_ENABLED=true` when friends need to create their own accounts. Registration is
available from the login page; usernames and password hashes are stored in the configured database,
never as plaintext passwords. Registered accounts can log out and sign in again, and their projects
remain scoped to their own identity. Set the flag back to `false` after the intended users have
registered to stop new sign-ups without disabling existing accounts. In the SQLite pilot profile,
account durability has the same `/mnt/workspace` limitations as project and dataset metadata.

ModelScope free hardware can sleep or expire and must not be presented as a 24×7 SLA. For a
long-lived public pilot, use external PostgreSQL and private S3/OSS even when the application
container remains on ModelScope, and treat cold starts as an expected platform state. The current
platform rules, audited Studio state and release gate are maintained in
[`MODELSCOPE_LONG_RUNNING.md`](./MODELSCOPE_LONG_RUNNING.md).

The single-container pilot is also fail-closed: at runtime it still requires a non-placeholder
`AUTH_MODE=jwt`, `JWT_SECRET`, `LOGIN_PASSWORD`, exact public `TRUSTED_HOSTS`, `CORS_ORIGINS`, and
the appropriate database/storage credentials. The image intentionally does not contain fallback production
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

Before opening access, run the repeatable small-traffic acceptance profile and retain its JSON
summary with the release record:

```bash
LOGIN_USERNAME='read-from-secret-manager' \
LOGIN_PASSWORD='read-from-secret-manager' \
python3 scripts/small_traffic_test.py \
  --base-url https://analytics.example.com \
  --requests 500 --concurrency 8 --require-authenticated
```

Thresholds, private-platform authentication and the test report template are documented in
[`../quality/SMALL_TRAFFIC_ACCEPTANCE.md`](../quality/SMALL_TRAFFIC_ACCEPTANCE.md).

Then run the disposable representative workflow to verify upload, quality, analysis, evidence and
report download using the same smoke account:

```bash
LOGIN_USERNAME='read-from-secret-manager' \
LOGIN_PASSWORD='read-from-secret-manager' \
python3 scripts/production_workflow_smoke.py \
  --base-url https://analytics.example.com
```

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
