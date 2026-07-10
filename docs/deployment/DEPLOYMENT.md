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
DATA_ROOT=/mnt/workspace/data
DATABASE_URL=sqlite:////mnt/workspace/data/app.db
SESSION_COOKIE_SECURE=true
PORT=7860
```

ModelScope must use the Docker SDK, and the account must have completed the
platform's Docker build prerequisites. Uploaded data and generated artifacts use
`/mnt/workspace/data`; use an external database and object storage for stronger
durability guarantees.

Current production deployment:

- Studio: `https://www.modelscope.cn/studios/Ascano/ai-data-analyst-agent`
- Application: `https://ascano-ai-data-analyst-agent.ms.show`
- Visibility: public Studio endpoint with application-level JWT authentication
- Storage: SQLite, datasets, and generated artifacts under `/mnt/workspace/data`
- Verified: health, login, authenticated capabilities, CSV ingestion, full
  analysis run, and artifact persistence within the active Studio workspace

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
