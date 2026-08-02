#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/golos-support}"
APP_USER="${APP_USER:-golos-support}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-codex/server-stt-profile}"
SERVICE_NAME="${SERVICE_NAME:-golos-support}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

cd "${APP_DIR}"
runuser -u "${APP_USER}" -- git fetch origin "${DEPLOY_BRANCH}"
runuser -u "${APP_USER}" -- git checkout "${DEPLOY_BRANCH}"
runuser -u "${APP_USER}" -- git pull --ff-only origin "${DEPLOY_BRANCH}"

runuser -u "${APP_USER}" -- "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/support_server/requirements.txt"

systemctl restart "${SERVICE_NAME}"
sleep 2
bash "${APP_DIR}/deploy/scripts/health_check.sh"
