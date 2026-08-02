#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
SERVICE_NAME="${SERVICE_NAME:-golos-support}"
PRE_RESTORE_BACKUP_DIR="${PRE_RESTORE_BACKUP_DIR:-/var/backups/golos-support/pre-restore}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if [[ -z "${ARCHIVE}" || ! -f "${ARCHIVE}" ]]; then
  echo "Usage: CONFIRM_RESTORE=yes $0 /path/to/golos-support-backup.tar.gz" >&2
  exit 1
fi

if [[ "${CONFIRM_RESTORE:-}" != "yes" ]]; then
  echo "Set CONFIRM_RESTORE=yes to restore files from archive." >&2
  exit 1
fi

install -d -m 700 "${PRE_RESTORE_BACKUP_DIR}"
if [[ -d /etc/golos-support || -d /var/lib/golos-support ]]; then
  tar -czf "${PRE_RESTORE_BACKUP_DIR}/before-restore-$(date +%Y%m%d-%H%M%S).tar.gz" \
    --ignore-failed-read \
    /etc/golos-support \
    /var/lib/golos-support
fi

systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
tar -xzf "${ARCHIVE}" -C /

chown -R golos-support:golos-support /var/lib/golos-support /opt/golos-support 2>/dev/null || true
chmod 640 /etc/golos-support/golos-support.env 2>/dev/null || true

systemctl daemon-reload
nginx -t
systemctl restart "${SERVICE_NAME}"
systemctl reload nginx

echo "Restore complete."
