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
- The token is stored only in server env and local user `.env`.
- Do not commit `.env`, server env files, diagnostic ZIP files, SQLite data, SSH keys, or production backups.
- Diagnostic ZIP validation rejects `.env`, audio files, `temp/`, and `models/`.

## Checks

```bash
systemctl is-active golos-support
systemctl status golos-support
curl -fsS http://127.0.0.1:8765/health
curl -fsS https://golos.msgcrm.ru/health
curl -fsS https://golos.msgcrm.ru/api/update
nginx -t
certbot certificates
```

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
