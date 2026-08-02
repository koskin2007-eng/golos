# Golos Server Deployment

Infrastructure templates for moving the Golos support server to a new Ubuntu VPS.

These files are safe to commit: they contain paths, defaults, and placeholders, but no
production tokens, passwords, API keys, YooMoney secrets, SSH keys, or database dumps.

## Layout

```text
deploy/
  env/golos-support.env.example
  nginx/golos-support.http.conf
  systemd/golos-support.service
  scripts/install_support_server.sh
  scripts/deploy_update.sh
  scripts/backup_data.sh
  scripts/restore_data.sh
  scripts/health_check.sh
```

## Default Production Paths

```text
/opt/golos-support
/etc/golos-support/golos-support.env
/var/lib/golos-support
/etc/systemd/system/golos-support.service
/etc/nginx/sites-available/golos-support
```

## New Server Bootstrap

Run as `root` on a clean Ubuntu server:

```bash
export APP_DOMAIN=golos.msgcrm.ru
export DEPLOY_BRANCH=codex/server-stt-profile
bash deploy/scripts/install_support_server.sh
```

Then edit secrets manually on the server:

```bash
nano /etc/golos-support/golos-support.env
```

Do not paste real values into Git, issue comments, or Codex chat.

## Backup Old Server

Run on the old server:

```bash
bash /opt/golos-support/deploy/scripts/backup_data.sh
```

Copy the produced archive to the new server through a secure channel.

## Restore On New Server

Run on the new server:

```bash
CONFIRM_RESTORE=yes bash /opt/golos-support/deploy/scripts/restore_data.sh /path/to/golos-support-backup-YYYYmmdd-HHMMSS.tar.gz
```

## Check

```bash
bash /opt/golos-support/deploy/scripts/health_check.sh
```

For HTTPS after DNS points to the new server, issue a certificate with Certbot and
recheck:

```bash
certbot --nginx -d golos.msgcrm.ru
bash /opt/golos-support/deploy/scripts/health_check.sh
```
