FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
RUN --mount=type=cache,id=frontend-corepack-cache,target=/root/.cache/node/corepack \
    corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=frontend-pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --frozen-lockfile
COPY frontend/ ./
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_MODE=real
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_API_MODE=${VITE_API_MODE}
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.11.26 AS uv

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    API_PREFIX=/api/v1 \
    AUTH_MODE=jwt \
    JOB_EXECUTION_MODE=worker \
    DATA_ROOT=/mnt/workspace/data \
    DATABASE_URL=sqlite:////mnt/workspace/data/app.db \
    FRONTEND_DIST_DIR=/app/frontend-dist \
    MAX_UPLOAD_BYTES=104857600 \
    SESSION_COOKIE_SECURE=true \
    PORT=7860

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/README.md backend/alembic.ini ./
COPY backend/uv.lock ./
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY --from=uv /uv /uvx /bin/
RUN --mount=type=cache,id=backend-uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --link-mode=copy \
    && rm -f /bin/uv /bin/uvx
COPY --from=frontend-build /build/frontend/dist ./frontend-dist
COPY scripts/pilot-entrypoint.sh /usr/local/bin/pilot-entrypoint

RUN mkdir -p /mnt/workspace/data /tmp/datatrace-storage-cache \
    && chown -R app:app /mnt/workspace/data /tmp/datatrace-storage-cache \
    && chmod 0755 /usr/local/bin/pilot-entrypoint

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 7860
ENTRYPOINT ["pilot-entrypoint"]
CMD ["python", "-m", "app.production"]
