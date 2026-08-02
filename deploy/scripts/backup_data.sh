#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/golos-support}"
APP_DIR="${APP_DIR:-/opt/golos-support}"
DATA_DIR="${DATA_DIR:-/var/lib/golos-support}"
ENV_DIR="${ENV_DIR:-/etc/golos-support}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_DIR}/golos-support-backup-${TIMESTAMP}.tar.gz"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

install -d -m 700 "${BACKUP_DIR}"

tar -czf "${ARCHIVE}" \
  --ignore-failed-read \
  "${ENV_DIR}" \
  "${DATA_DIR}" \
  /etc/systemd/system/golos-support.service \
  /etc/nginx/sites-available/golos-support \
  /etc/nginx/sites-enabled/golos-support

sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
chmod 600 "${ARCHIVE}" "${ARCHIVE}.sha256"

echo "Backup archive: ${ARCHIVE}"
echo "Checksum: ${ARCHIVE}.sha256"
echo "Copy it to the new server through a secure channel."
