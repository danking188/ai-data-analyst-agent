#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_dir="${repo_root}/deploy/aliyun-lite"
env_file="${profile_dir}/.env"
compose_file="${profile_dir}/docker-compose.yml"

if [[ ! -f "${env_file}" ]]; then
  echo "Missing ${env_file}; copy env.example to .env and replace every placeholder." >&2
  exit 1
fi

if [[ "$(stat -c '%a' "${env_file}")" != "600" ]]; then
  echo "${env_file} must have mode 600." >&2
  exit 1
fi

if grep -Eq 'example\.com|replace-with-' "${env_file}"; then
  echo "Refusing to deploy while example domains or placeholder secrets remain." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${env_file}" | tail -n 1
}

domain="$(read_env_value DOMAIN)"
cors_origins="$(read_env_value CORS_ORIGINS)"
trusted_hosts="$(read_env_value TRUSTED_HOSTS)"
data_dir="$(read_env_value DATATRACE_DATA_DIR)"
backup_dir="$(read_env_value DATATRACE_BACKUP_DIR)"

if [[ -z "${domain}" || "${cors_origins}" != "https://${domain}" ]]; then
  echo "CORS_ORIGINS must exactly equal https://DOMAIN." >&2
  exit 1
fi

case ",${trusted_hosts}," in
  *",${domain},"*) ;;
  *) echo "TRUSTED_HOSTS must include DOMAIN exactly." >&2; exit 1 ;;
esac

install -d -m 0750 "${data_dir:-/opt/datatrace/data}" "${backup_dir:-/opt/datatrace/backups}"

docker compose --env-file "${env_file}" -f "${compose_file}" config --quiet
docker compose --env-file "${env_file}" -f "${compose_file}" build
docker compose --env-file "${env_file}" -f "${compose_file}" up -d --remove-orphans
# Caddy runs with its admin API disabled, so a restart is required to load a changed bind-mounted
# Caddyfile. Existing TLS state remains in the named volume.
docker compose --env-file "${env_file}" -f "${compose_file}" restart caddy
docker compose --env-file "${env_file}" -f "${compose_file}" ps
systemctl start datatrace-backup.service

echo "Waiting for HTTPS readiness at https://${domain}/api/v1/health/ready"
for attempt in {1..24}; do
  if curl --fail --silent --show-error --max-time 10 \
    "https://${domain}/api/v1/health/ready" >/dev/null; then
    echo "Aliyun lite deployment is ready at https://${domain}"
    exit 0
  fi
  sleep 5
done

echo "Deployment did not become ready within two minutes." >&2
docker compose --env-file "${env_file}" -f "${compose_file}" logs --tail=200 >&2
exit 1
