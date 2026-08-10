#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_files=(
  docs/development/PROJECT_STATUS.md
  docs/deployment/PRODUCTION_READINESS.md
  docs/api/openapi.yaml
  backend/uv.lock
  backend/.env.example
  frontend/pnpm-lock.yaml
  frontend/.env.example
)
for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    printf 'Required release file is missing: %s\n' "$required_file" >&2
    exit 1
  fi
done

legacy_files=(
  docs/development/BACKEND_SESSION_PROMPT.md
  docs/development/FRONTEND_SESSION_PROMPT.md
  frontend/src/features/placeholder/WorkflowPlaceholder.tsx
  scripts/persistence_smoke.sh
)
for legacy_file in "${legacy_files[@]}"; do
  if [[ -e "$legacy_file" ]]; then
    printf 'Removed legacy file has returned: %s\n' "$legacy_file" >&2
    exit 1
  fi
done

tracked_artifacts="$({
  git ls-files
} | awk '
  /(^|\/)__pycache__(\/|$)/ ||
  /(^|\/)\.pytest_cache(\/|$)/ ||
  /(^|\/)\.mypy_cache(\/|$)/ ||
  /(^|\/)\.ruff_cache(\/|$)/ ||
  /(^|\/)node_modules(\/|$)/ ||
  /(^|\/)dist(\/|$)/ ||
  /(^|\/)output\/playwright(\/|$)/ ||
  /(^|\/)\.DS_Store$/ ||
  /\.py[co]$/ ||
  /(^|\/)\.coverage(\.|$)/ {
    print
  }
')"
if [[ -n "$tracked_artifacts" ]]; then
  printf 'Generated artifacts must not be tracked:\n%s\n' "$tracked_artifacts" >&2
  exit 1
fi

if git ls-files --error-unmatch .env.production.local >/dev/null 2>&1; then
  printf '.env.production.local must remain untracked.\n' >&2
  exit 1
fi

printf 'Repository hygiene checks passed.\n'
