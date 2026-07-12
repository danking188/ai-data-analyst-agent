# Deployment Guide

This project ships as two deployable services:

- `backend`: FastAPI API, Alembic migrations, SQLite or SQLAlchemy-compatible database.
- `frontend`: Vite static build served by Nginx, with `/api/v1/*` proxied to the backend.

## Local Docker Deployment

Create a deployment environment file:

```bash
cp .env.deploy.example .env.deploy
```

Edit `.env.deploy` before exposing the service:

- Set `DEV_AUTH_TOKEN` to a long random value.
- Set `JWT_SECRET` to a long random value.
- Set `CORS_ORIGINS` to the public frontend origin.
- Keep `VITE_API_BASE_URL=/api/v1` when using the bundled Nginx proxy.

Build and start:

```bash
docker compose --env-file .env.deploy up --build
```

Open:

- Frontend: <http://localhost:8080>
- Backend health: <http://localhost:8000/api/v1/health>

Run deployment smoke checks:

```bash
DEV_AUTH_TOKEN="$(grep '^DEV_AUTH_TOKEN=' .env.deploy | cut -d= -f2-)" ./scripts/deploy_smoke.sh
```

Stop:

```bash
docker compose --env-file .env.deploy down
```

Runtime data is stored in the `backend-data` Docker volume.

## Production Notes

The current baseline is suitable for local servers, internal demos, and first cloud migration.
Before internet-facing production traffic, finish these hardening tasks:

- Replace `AUTH_MODE=dev_token` with JWT validation and remove dev tokens from frontend builds.
- Move from SQLite to a managed database when concurrent writes or backups matter.
- Terminate TLS at a reverse proxy or cloud load balancer.
- Configure persistent object storage for uploaded datasets and generated artifacts.
- Export structured logs and add uptime/error monitoring.
- Run `alembic upgrade head` as a release step before serving traffic.

## Single-container Public Deployment

The root `Dockerfile` is the production entry point for platforms that expose one
container. It builds the React frontend, serves it from FastAPI, exposes the API
under `/api/v1`, and listens on `0.0.0.0:${PORT:-7860}`.

Required runtime secrets:

- `LOGIN_USERNAME`: the account shown on the login page.
- `LOGIN_PASSWORD`: a strong password stored only in the platform secret manager.
- `JWT_SECRET`: at least 32 random bytes used to sign login and download tokens.
- `REGISTRATION_ENABLED`: set to `true` to allow persistent self-service accounts.

Startup deliberately fails when `LOGIN_PASSWORD` or `JWT_SECRET` is missing,
too short, or still uses an example placeholder.

Recommended runtime values for ModelScope Studio:

```text
APP_ENV=production
AUTH_MODE=jwt
REGISTRATION_ENABLED=true
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_RECYCLE_SECONDS=300
REQUIRE_EXTERNAL_PERSISTENCE=true
JOB_EXECUTION_MODE=worker
STORAGE_BACKEND=s3
STORAGE_CACHE_ROOT=/tmp/datatrace-storage-cache
S3_BUCKET=private-bucket
S3_ENDPOINT_URL=https://s3-compatible-endpoint
S3_REGION=auto
S3_ACCESS_KEY_ID=secret
S3_SECRET_ACCESS_KEY=secret
S3_PREFIX=datatrace
S3_FORCE_PATH_STYLE=true
# Leave empty for Supabase Storage. Use AES256 only when the provider supports it.
S3_SERVER_SIDE_ENCRYPTION=
SESSION_COOKIE_SECURE=true
PORT=7860
```

`JOB_EXECUTION_MODE=worker` keeps long-running work out of API request processes. The
production entrypoint supervises both the API and the database-backed worker; queued jobs
remain in PostgreSQL and can be claimed after restarts.

ModelScope must use the Docker SDK, and the account must have completed the
platform's Docker build prerequisites. Production metadata uses external PostgreSQL;
uploaded data and generated artifacts use private S3-compatible object storage. The
container only keeps a disposable local cache under `STORAGE_CACHE_ROOT`.

Release gates:

- `GET /api/v1/health/ready` reports PostgreSQL and object storage as ready.
- `alembic upgrade head` succeeds against PostgreSQL before Uvicorn starts.
- A registered account can log in before and after a complete Studio redeployment.
- An uploaded dataset and exported artifact can be read after the local cache is cleared.

Current production deployment:

- Studio: `https://www.modelscope.cn/studios/Ascano/ai-data-analyst-agent`
- Application: `https://ascano-ai-data-analyst-agent.ms.show`
- Visibility: public Studio endpoint with application-level JWT authentication
- Storage: external PostgreSQL plus private Supabase S3-compatible object storage
- Worker: database-backed runner supervised beside the API process
- Verified: health, login, registration, CSV ingestion, cleaning, full analysis
  run, artifact persistence, and cross-deployment account/data recovery

The real modeling runtime additionally installs scikit-learn, SciPy and joblib. A model run
produces a protected downloadable model Artifact, so the S3 credentials must permit object
creation and retrieval under `S3_PREFIX`.

Build and test the single-container image locally:

```bash
docker build -t ai-data-analyst-public .
docker run --rm -p 7860:7860 \
  -e LOGIN_USERNAME=analyst \
  -e LOGIN_PASSWORD=change-me \
  -e JWT_SECRET=replace-with-at-least-32-random-characters \
  -e SESSION_COOKIE_SECURE=false \
  ai-data-analyst-public

FRONTEND_URL=http://localhost:7860 \
BACKEND_URL=http://localhost:7860/api/v1 \
LOGIN_USERNAME=analyst LOGIN_PASSWORD=change-me \
./scripts/deploy_smoke.sh
```

## Platform Mapping

For a single VM, use the included `docker-compose.yml`.

For managed platforms:

- Backend command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Backend health path: `/api/v1/health`
- Frontend build command: `pnpm install --frozen-lockfile && pnpm build`
- Frontend output directory: `frontend/dist`
- Required frontend build env: `VITE_API_BASE_URL`, `VITE_API_MODE=real`
