#!/usr/bin/env sh
set -eu

FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000/api/v1}"
AUTH_TOKEN="${AUTH_TOKEN:-${DEV_AUTH_TOKEN:-local-development-token}}"

cleanup_files=""
cleanup() {
  for cleanup_file in $cleanup_files; do
    rm -f "$cleanup_file"
  done
}
trap cleanup EXIT HUP INT TERM

if [ -n "${COOKIE_JAR:-}" ]; then
  cookie_jar="$COOKIE_JAR"
else
  cookie_jar="$(mktemp "${TMPDIR:-/tmp}/datatrace-smoke-cookie.XXXXXX")"
  cleanup_files="$cleanup_files $cookie_jar"
fi
chmod 600 "$cookie_jar"

headers_file="$(mktemp "${TMPDIR:-/tmp}/datatrace-smoke-headers.XXXXXX")"
cleanup_files="$cleanup_files $headers_file"

echo "Checking backend health at ${BACKEND_URL}/health"
curl -fsS "${BACKEND_URL}/health" >/dev/null
curl -fsS "${BACKEND_URL}/health/ready" >/dev/null

echo "Checking authenticated backend capabilities"
if [ -n "${LOGIN_USERNAME:-}" ] && [ -n "${LOGIN_PASSWORD:-}" ]; then
  login_request="$(mktemp "${TMPDIR:-/tmp}/datatrace-smoke-login.XXXXXX")"
  cleanup_files="$cleanup_files $login_request"
  chmod 600 "$login_request"
  LOGIN_USERNAME="$LOGIN_USERNAME" LOGIN_PASSWORD="$LOGIN_PASSWORD" python3 -c \
    'import json, os; print(json.dumps({"username": os.environ["LOGIN_USERNAME"], "password": os.environ["LOGIN_PASSWORD"]}))' \
    >"$login_request"
  curl -fsS -c "$cookie_jar" \
    -H "Content-Type: application/json" \
    --data-binary "@$login_request" \
    "${BACKEND_URL}/auth/login" >/dev/null
  curl -fsS -b "$cookie_jar" "${BACKEND_URL}/auth/session" >/dev/null
  curl -fsS -b "$cookie_jar" "${BACKEND_URL}/system/capabilities" >/dev/null
else
  curl -fsS \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${BACKEND_URL}/system/capabilities" >/dev/null
fi

echo "Checking frontend entry at ${FRONTEND_URL}"
curl -fsS -D "$headers_file" -o /dev/null "${FRONTEND_URL}"

for required_header in \
  "x-content-type-options:" \
  "x-frame-options:" \
  "referrer-policy:" \
  "permissions-policy:" \
  "content-security-policy:"
do
  if ! grep -qi "^${required_header}" "$headers_file"; then
    echo "Missing required security header: ${required_header%:}" >&2
    exit 1
  fi
done

case "$FRONTEND_URL" in
  https://*)
    if ! grep -qi '^strict-transport-security:' "$headers_file"; then
      echo "Missing Strict-Transport-Security on HTTPS frontend" >&2
      exit 1
    fi
    ;;
esac

echo "Checking frontend API proxy at ${FRONTEND_URL}/api/v1/health"
curl -fsS "${FRONTEND_URL}/api/v1/health" >/dev/null

echo "Deployment smoke checks passed."
