#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-golos-support}"
APP_GROUP="${APP_GROUP:-golos-support}"
APP_DIR="${APP_DIR:-/opt/golos-support}"
DATA_DIR="${DATA_DIR:-/var/lib/golos-support}"
ENV_DIR="${ENV_DIR:-/etc/golos-support}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/golos-support.env}"
REPO_URL="${REPO_URL:-https://github.com/koskin2007-eng/golos.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-codex/server-stt-profile}"
APP_DOMAIN="${APP_DOMAIN:-golos.msgcrm.ru}"
APP_PORT="${APP_PORT:-8765}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

echo "Installing packages..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx curl ca-certificates

if ! getent group "${APP_GROUP}" >/dev/null; then
  groupadd --system "${APP_GROUP}"
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --gid "${APP_GROUP}" --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}" "${DATA_DIR}"
install -d -m 750 -o root -g "${APP_GROUP}" "${ENV_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  echo "Updating existing checkout..."
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" fetch origin "${DEPLOY_BRANCH}"
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" checkout "${DEPLOY_BRANCH}"
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" pull --ff-only origin "${DEPLOY_BRANCH}"
else
  if find "${APP_DIR}" -mindepth 1 -maxdepth 1 | grep -q .; then
    echo "${APP_DIR} is not empty and is not a git checkout." >&2
    exit 1
  fi
  echo "Cloning ${REPO_URL}..."
  runuser -u "${APP_USER}" -- git clone --branch "${DEPLOY_BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}" "${DATA_DIR}"

echo "Preparing Python environment..."
runuser -u "${APP_USER}" -- python3 -m venv "${APP_DIR}/.venv"
runuser -u "${APP_USER}" -- "${APP_DIR}/.venv/bin/pip" install --upgrade pip
runuser -u "${APP_USER}" -- "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/support_server/requirements.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 640 -o root -g "${APP_GROUP}" "${APP_DIR}/deploy/env/golos-support.env.example" "${ENV_FILE}"
  sed -i "s#GOLOS_PUBLIC_APP_URL=.*#GOLOS_PUBLIC_APP_URL=https://${APP_DOMAIN}#g" "${ENV_FILE}"
  echo "Created ${ENV_FILE}. Fill secrets before production use."
else
  echo "Keeping existing ${ENV_FILE}."
fi

install -m 644 "${APP_DIR}/deploy/systemd/golos-support.service" /etc/systemd/system/golos-support.service

sed \
  -e "s#__DOMAIN__#${APP_DOMAIN}#g" \
  -e "s#__APP_PORT__#${APP_PORT}#g" \
  "${APP_DIR}/deploy/nginx/golos-support.http.conf" > /etc/nginx/sites-available/golos-support
ln -sfn /etc/nginx/sites-available/golos-support /etc/nginx/sites-enabled/golos-support

systemctl daemon-reload
systemctl enable golos-support

nginx -t
systemctl restart golos-support
systemctl reload nginx

echo "Installed. Next:"
echo "  1. Edit ${ENV_FILE} and fill secrets."
echo "  2. Run: systemctl restart golos-support"
echo "  3. Run: bash ${APP_DIR}/deploy/scripts/health_check.sh"
echo "  4. After DNS cutover: certbot --nginx -d ${APP_DOMAIN}"
