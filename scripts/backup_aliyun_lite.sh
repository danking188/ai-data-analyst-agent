#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_dir="${repo_root}/deploy/aliyun-lite"
env_file="${profile_dir}/.env"
compose_file="${profile_dir}/docker-compose.yml"

if [[ ! -r "${env_file}" ]]; then
  echo "Backup skipped: ${env_file} is unavailable." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${env_file}" | tail -n 1
}

data_dir="$(read_env_value DATATRACE_DATA_DIR)"
backup_dir="$(read_env_value DATATRACE_BACKUP_DIR)"
data_dir="${data_dir:-/opt/datatrace/data}"
backup_dir="${backup_dir:-/opt/datatrace/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
sqlite_tmp="${backup_dir}/.app-${timestamp}.sqlite.tmp"
sqlite_backup="${backup_dir}/app-${timestamp}.sqlite"
files_backup="${backup_dir}/files-${timestamp}.tar.gz"

install -d -m 0750 "${backup_dir}"
cleanup() { rm -f "${sqlite_tmp}"; }
trap cleanup EXIT

docker compose --env-file "${env_file}" -f "${compose_file}" exec -T app \
  python -c "import sqlite3; src=sqlite3.connect('file:/mnt/workspace/data/app.db?mode=ro', uri=True); dst=sqlite3.connect('/mnt/workspace/backups/.app-${timestamp}.sqlite.tmp'); src.backup(dst); result=dst.execute('PRAGMA quick_check').fetchone()[0]; dst.close(); src.close(); assert result == 'ok', result"

mv "${sqlite_tmp}" "${sqlite_backup}"
tar --exclude='./app.db' --exclude='./app.db-wal' --exclude='./app.db-shm' \
  -C "${data_dir}" -czf "${files_backup}" .
sha256sum "${sqlite_backup}" "${files_backup}" >"${backup_dir}/backup-${timestamp}.sha256"

# Keep two weeks of local recovery points. Off-server backups should have their own policy.
find "${backup_dir}" -type f \
  \( -name 'app-*.sqlite' -o -name 'files-*.tar.gz' -o -name 'backup-*.sha256' \) \
  -mtime +14 -delete

echo "Backup completed: ${timestamp}"
