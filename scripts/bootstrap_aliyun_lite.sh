#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root (for example: sudo ./scripts/bootstrap_aliyun_lite.sh)." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Unsupported host: /etc/os-release is missing." >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "This bootstrap is intentionally limited to Ubuntu hosts." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl docker.io docker-compose-v2 fail2ban ufw

systemctl enable --now docker
systemctl enable --now fail2ban

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

if [[ -z "$(swapon --show --noheadings)" ]]; then
  if [[ ! -e /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  if ! grep -Fq '/swapfile none swap sw 0 0' /etc/fstab; then
    printf '%s\n' '/swapfile none swap sw 0 0' >>/etc/fstab
  fi
fi

install -d -m 0750 /opt/datatrace /opt/datatrace/data /opt/datatrace/backups

install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/systemd/datatrace-backup.service" \
  /etc/systemd/system/datatrace-backup.service
install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/systemd/datatrace-backup.timer" \
  /etc/systemd/system/datatrace-backup.timer
install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/systemd/datatrace-health.service" \
  /etc/systemd/system/datatrace-health.service
install -m 0644 "$(dirname "${BASH_SOURCE[0]}")/systemd/datatrace-health.timer" \
  /etc/systemd/system/datatrace-health.timer
systemctl daemon-reload
systemctl enable --now datatrace-backup.timer datatrace-health.timer

echo "Host bootstrap complete. Docker, firewall, fail2ban, swap, backups and health monitoring are ready."
