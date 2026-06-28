# Golos Support Server

## Production deployment

Current production endpoint:

```text
https://golos.msgcrm.ru
```

Server layout:

```text
/opt/golos-support                 # git checkout
/etc/golos-support/golos-support.env
/var/lib/golos-support             # SQLite and diagnostic ZIP files
/etc/systemd/system/golos-support.service
/etc/nginx/sites-available/golos-support
```

Runtime:

- systemd service: `golos-support`
- local listen address: `127.0.0.1:8765`
- public proxy: nginx HTTPS on `golos.msgcrm.ru`
- token source: `GOLOS_SUPPORT_TOKEN` in the server env file

Production checks:

```bash
systemctl status golos-support
curl -fsS http://127.0.0.1:8765/health
curl -fsS https://golos.msgcrm.ru/health
curl -fsS https://golos.msgcrm.ru/api/update
nginx -t
certbot certificates
```

Do not commit server env files, support tokens, diagnostic archives, SQLite data, SSH keys, or production backups.

Минимальный сервер поддержки для проекта "Голос".

## Что умеет

- `GET /health` - проверка, что сервер жив.
- `POST /api/diagnostics` - принимает diagnostic ZIP от приложения.
- `POST /api/events` - принимает технические события.
- `GET /api/update` - отдаёт `latest.json` из локального файла или проксирует публичный GitHub Release.

## Локальный запуск

```powershell
.\support_server\run_local.ps1
```

После запуска:

```text
http://127.0.0.1:8765/health
```

## Настройки окружения

- `GOLOS_SUPPORT_DATA_DIR` - папка данных, по умолчанию `support_server/data`.
- `GOLOS_SUPPORT_TOKEN` - если задан, запросы к `/api/diagnostics` и `/api/events` требуют `Authorization: Bearer ...`.
- `GOLOS_MAX_UPLOAD_MB` - максимальный размер diagnostic ZIP, по умолчанию `25`.
- `GOLOS_UPDATE_JSON_PATH` - локальный `latest.json` для `/api/update`.
- `GOLOS_PUBLIC_LATEST_JSON_URL` - публичный fallback `latest.json`.

## Подключение приложения

В локальном `config.yaml`:

```yaml
support:
  server_url: "https://support.example.ru"
  token_env: "GOLOS_SUPPORT_TOKEN"
```

Токен хранить только в `.env`:

```text
GOLOS_SUPPORT_TOKEN=...
```

Если `support.server_url` пустой, приложение продолжит открывать GitHub Issue и папку с diagnostic ZIP.

## Безопасность

Сервер отвергает diagnostic ZIP, если внутри есть `.env`, временное аудио, папки `temp/` или `models/`.
Сам OpenAI API key не должен отправляться ни в архиве, ни отдельным полем.
