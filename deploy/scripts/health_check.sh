#!/usr/bin/env bash
set -euo pipefail

APP_DOMAIN="${APP_DOMAIN:-golos.msgcrm.ru}"
APP_PORT="${APP_PORT:-8765}"
SERVICE_NAME="${SERVICE_NAME:-golos-support}"

echo "Checking systemd..."
systemctl is-active --quiet "${SERVICE_NAME}"
systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,12p'

echo "Checking local HTTP..."
curl -fsS "http://127.0.0.1:${APP_PORT}/health"
echo

echo "Checking public HTTP(S)..."
if curl -fsS "https://${APP_DOMAIN}/health"; then
  echo
else
  curl -fsS "http://${APP_DOMAIN}/health"
  echo
fi

echo "Checking update endpoint..."
curl -fsS "http://127.0.0.1:${APP_PORT}/api/update" >/dev/null

echo "Checking nginx config..."
nginx -t

echo "OK"
