#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKEND_DIR="$ROOT_DIR/backend"
UV_BIN=${UV_BIN:-uv}

if ! command -v "$UV_BIN" >/dev/null 2>&1; then
  echo "uv is required; install it from https://docs.astral.sh/uv/ first" >&2
  exit 2
fi

cd "$BACKEND_DIR"
"$UV_BIN" sync --frozen --extra dev

echo "Backend dependencies synchronized from backend/uv.lock"
