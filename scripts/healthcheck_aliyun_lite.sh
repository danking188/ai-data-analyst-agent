#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_dir="${repo_root}/deploy/aliyun-lite"
env_file="${profile_dir}/.env"
compose_file="${profile_dir}/docker-compose.yml"
failure_file=/run/datatrace-health-failures

if docker compose --env-file "${env_file}" -f "${compose_file}" exec -T app \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/v1/health/ready', timeout=8).read()"; then
  rm -f "${failure_file}"
  exit 0
fi

failures=0
if [[ -r "${failure_file}" ]]; then
  failures="$(cat "${failure_file}")"
fi
failures=$((failures + 1))
printf '%s\n' "${failures}" >"${failure_file}"

if (( failures >= 3 )); then
  echo "Readiness failed ${failures} consecutive times; restarting the app container." >&2
  docker compose --env-file "${env_file}" -f "${compose_file}" restart app
  rm -f "${failure_file}"
  exit 1
fi

echo "Readiness failed (${failures}/3); waiting for the next check." >&2
exit 1
