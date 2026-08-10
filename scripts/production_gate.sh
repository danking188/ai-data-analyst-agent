#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${ENV_FILE:-$repo_root/.env.deploy}"
if [[ ! -f "$env_file" ]]; then
  printf 'Deployment environment file does not exist: %s\n' "$env_file" >&2
  exit 2
fi

cd "$repo_root"
ruby scripts/validate_openapi.rb docs/api/openapi.yaml
docker compose --env-file "$env_file" config --quiet

cd backend
uv sync --frozen --extra dev
uv run ruff check app tests
uv run mypy app
uv run pytest --cov=app --cov-fail-under=80

cd ../frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build

printf 'All local production gates passed. External TLS, backup restore, alerts, and canary checks remain environment-specific.\n'
