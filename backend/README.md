# AI Data Analyst Agent Backend

FastAPI + SQLAlchemy 2 + Alembic backend, implemented against
[`../docs/api/openapi.yaml`](../docs/api/openapi.yaml).

Database structure, invariants, and Repository usage are documented in
[`../docs/data/BACKEND_DATABASE_IMPLEMENTATION.md`](../docs/data/BACKEND_DATABASE_IMPLEMENTATION.md).

## Local setup

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Development authorization:

```text
Authorization: Bearer local-development-token
```

## Quality checks

```bash
.venv/bin/ruff check .
.venv/bin/mypy app
.venv/bin/pytest
ruby ../scripts/validate_openapi.rb ../docs/api/openapi.yaml
```

The application never calls `metadata.create_all()`. Database schema changes
must be made through Alembic migrations.
