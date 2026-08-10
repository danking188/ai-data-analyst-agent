#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_FILE:?BACKUP_FILE must identify one pg_dump custom archive}"

if [[ "${CONFIRM_RESTORE:-}" != "RESTORE_DATATRACE_DATABASE" ]]; then
  printf 'Refusing destructive restore. Set CONFIRM_RESTORE=RESTORE_DATATRACE_DATABASE.\n' >&2
  exit 2
fi
if [[ ! -f "$BACKUP_FILE" || ! -f "$BACKUP_FILE.sha256" ]]; then
  printf 'Backup archive or checksum file is missing.\n' >&2
  exit 2
fi

(cd "$(dirname "$BACKUP_FILE")" && sha256sum --check "$(basename "$BACKUP_FILE").sha256")
pg_restore --list "$BACKUP_FILE" >/dev/null
pg_restore --dbname="$DATABASE_URL" --clean --if-exists --no-owner --no-acl --exit-on-error "$BACKUP_FILE"
printf 'Restore completed and archive checksum verified.\n'
