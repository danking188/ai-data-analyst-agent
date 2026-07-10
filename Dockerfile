FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
RUN --mount=type=cache,id=npm-cache,target=/root/.npm \
    npm install --global pnpm@10.12.1 --fetch-retries=5
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --frozen-lockfile
COPY frontend/ ./
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_MODE=real
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_API_MODE=${VITE_API_MODE}
RUN pnpm build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    API_PREFIX=/api/v1 \
    AUTH_MODE=jwt \
    DATA_ROOT=/mnt/workspace/data \
    DATABASE_URL=sqlite:////mnt/workspace/data/app.db \
    FRONTEND_DIST_DIR=/app/frontend-dist \
    SESSION_COOKIE_SECURE=true \
    PORT=7860

WORKDIR /app
COPY backend/pyproject.toml backend/README.md backend/alembic.ini ./
COPY backend/app ./app
COPY backend/migrations ./migrations
RUN pip install --upgrade pip && pip install .
COPY --from=frontend-build /build/frontend/dist ./frontend-dist

EXPOSE 7860
CMD ["sh", "-c", "mkdir -p ${DATA_ROOT} && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
