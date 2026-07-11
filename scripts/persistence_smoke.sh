#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:7860/api/v1}"
MODE="${1:-verify}"
: "${PERSISTENCE_PROBE_USERNAME:?PERSISTENCE_PROBE_USERNAME is required}"
: "${PERSISTENCE_PROBE_PASSWORD:?PERSISTENCE_PROBE_PASSWORD is required}"

[[ "$PERSISTENCE_PROBE_USERNAME" =~ ^[a-z0-9][a-z0-9_.-]{2,31}$ ]] || {
  printf 'PERSISTENCE_PROBE_USERNAME has an unsupported format\n' >&2
  exit 2
}
[[ "$PERSISTENCE_PROBE_PASSWORD" =~ ^[A-Za-z0-9._-]{12,128}$ ]] || {
  printf 'PERSISTENCE_PROBE_PASSWORD must use safe probe characters and be 12-128 chars\n' >&2
  exit 2
}

payload="$({
  printf '{"username":"%s","password":"%s"}' \
    "$PERSISTENCE_PROBE_USERNAME" "$PERSISTENCE_PROBE_PASSWORD"
})"
cookie_jar="$(mktemp /tmp/datatrace-persistence-cookie.XXXXXX)"
response_file="$(mktemp /tmp/datatrace-persistence-response.XXXXXX)"
trap 'rm -f "$cookie_jar" "$response_file"' EXIT

if [[ "$MODE" == "seed" ]]; then
  status="$(curl -sS -o "$response_file" -w '%{http_code}' \
    -c "$cookie_jar" -H 'Content-Type: application/json' \
    -d "$payload" "$BACKEND_URL/auth/register")"
  [[ "$status" == "201" ]] || {
    printf 'Persistence seed failed with HTTP %s\n' "$status" >&2
    exit 1
  }
  printf 'Persistence probe seeded. Redeploy the service, then run verify.\n'
  exit 0
fi

if [[ "$MODE" != "verify" ]]; then
  printf 'Usage: %s [seed|verify]\n' "$0" >&2
  exit 2
fi

status="$(curl -sS -o "$response_file" -w '%{http_code}' \
  -c "$cookie_jar" -H 'Content-Type: application/json' \
  -d "$payload" "$BACKEND_URL/auth/login")"
[[ "$status" == "200" ]] || {
  printf 'Persistence verification failed with HTTP %s\n' "$status" >&2
  exit 1
}
curl -fsS -b "$cookie_jar" "$BACKEND_URL/auth/session" >/dev/null
curl -fsS "$BACKEND_URL/health/ready" >/dev/null
printf 'Persistence verification passed.\n'
