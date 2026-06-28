# Golos Support Server Production

Production support server is deployed for Golos diagnostics.

## Public URL

```text
https://golos.msgcrm.ru
```

## Server Layout

```text
/opt/golos-support
/etc/golos-support/golos-support.env
/var/lib/golos-support
/etc/systemd/system/golos-support.service
/etc/nginx/sites-available/golos-support
```

## Runtime

- service: `golos-support`
- user: `golos-support`
- app listen address: `127.0.0.1:8765`
- public proxy: nginx HTTPS
- certificate: Let's Encrypt for `golos.msgcrm.ru`
- data store: SQLite and diagnostic ZIP files under `/var/lib/golos-support`

## Security

- `GOLOS_SUPPORT_TOKEN` is required for diagnostic and event uploads.
- `GOLOS_ADMIN_USERNAME` and an admin password are required for the diagnostics admin page.
- Admin password source is `GOLOS_ADMIN_PASSWORD`, or `GOLOS_ADMIN_TOKEN` when a separate password is not set.
- `OPENAI_API_KEY` is required on the server for premium transcription proxy.
- `GOLOS_PREMIUM_TRANSCRIBE_MODEL` can override the premium transcription model, default `gpt-4o-mini-transcribe`.
- Tokens and passwords are stored only in server env and local user `.env`.
- Do not commit `.env`, server env files, diagnostic ZIP files, SQLite data, SSH keys, or production backups.
- Diagnostic ZIP validation rejects `.env`, audio files, `temp/`, and `models/`.
- Public landing access to `/` is allowed. Admin diagnostics under `/admin` must stay protected by the server login.

## Checks

```bash
systemctl is-active golos-support
systemctl status golos-support
curl -fsS http://127.0.0.1:8765/health
curl -fsS https://golos.msgcrm.ru/health
curl -fsS https://golos.msgcrm.ru/api/update
curl -fsS https://golos.msgcrm.ru/
nginx -t
certbot certificates
```

## Private Diagnostics Admin

Server-side CLI:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli diagnostics --limit 20
./.venv/bin/python -m support_server.cli show REPORT_ID
```

Browser access:

```text
https://golos.msgcrm.ru/admin/login
```

Use `GOLOS_ADMIN_USERNAME` and the configured admin password from `/etc/golos-support/golos-support.env`.
Do not send these values in chat or commit them.

## Manual Premium MVP

Admin page:

```text
https://golos.msgcrm.ru/admin/premium
```

Create a 100 RUB manual package:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli premium create --label "Client name" --minutes 180 --amount-rub 100
```

List and top up:

```bash
./.venv/bin/python -m support_server.cli premium list
./.venv/bin/python -m support_server.cli premium grant LICENSE_ID --minutes 180 --amount-rub 100
```

Premium API:

```text
GET  /api/premium/balance
POST /api/premium/transcribe
GET  /api/client/actions
POST /api/client/actions/{action_id}/complete
```

The admin page can queue safe client actions for a premium key: request diagnostics or suggest update. The desktop app still asks the user before sending diagnostics.

## Desktop Connection

Local desktop config:

```yaml
support:
  server_url: https://golos.msgcrm.ru
  token_env: GOLOS_SUPPORT_TOKEN
```

Local `.env` must contain:

```text
GOLOS_SUPPORT_TOKEN=...
```

For paid users, desktop `.env` contains only:

```text
GOLOS_PREMIUM_KEY=...
```
