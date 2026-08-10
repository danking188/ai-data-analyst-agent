FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY pyproject.toml README.md alembic.ini ./
COPY uv.lock ./
COPY app ./app
COPY migrations ./migrations

COPY --from=uv /uv /uvx /bin/
RUN --mount=type=cache,id=backend-uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --link-mode=copy \
    && rm -f /bin/uv /bin/uvx

RUN mkdir -p /app/data /tmp/datatrace-storage-cache \
    && chown -R app:app /app/data /tmp/datatrace-storage-cache

USER app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
