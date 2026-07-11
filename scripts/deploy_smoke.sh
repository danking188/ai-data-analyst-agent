#!/usr/bin/env sh
set -eu

FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000/api/v1}"
AUTH_TOKEN="${AUTH_TOKEN:-${DEV_AUTH_TOKEN:-local-development-token}}"
COOKIE_JAR="${COOKIE_JAR:-/tmp/datatrace-smoke-cookie.txt}"

echo "Checking backend health at ${BACKEND_URL}/health"
curl -fsS "${BACKEND_URL}/health" >/dev/null
curl -fsS "${BACKEND_URL}/health/ready" >/dev/null

echo "Checking authenticated backend capabilities"
if [ -n "${LOGIN_USERNAME:-}" ] && [ -n "${LOGIN_PASSWORD:-}" ]; then
  curl -fsS -c "${COOKIE_JAR}" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${LOGIN_USERNAME}\",\"password\":\"${LOGIN_PASSWORD}\"}" \
    "${BACKEND_URL}/auth/login" >/dev/null
  curl -fsS -b "${COOKIE_JAR}" "${BACKEND_URL}/system/capabilities" >/dev/null
else
  curl -fsS \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${BACKEND_URL}/system/capabilities" >/dev/null
fi

echo "Checking frontend entry at ${FRONTEND_URL}"
curl -fsSI "${FRONTEND_URL}" >/dev/null

echo "Checking frontend API proxy at ${FRONTEND_URL}/api/v1/health"
curl -fsS "${FRONTEND_URL}/api/v1/health" >/dev/null

echo "Deployment smoke checks passed."
