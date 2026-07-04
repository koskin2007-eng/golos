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
- admin login source: `GOLOS_ADMIN_USERNAME` in the server env file, default `admin`
- admin password source: `GOLOS_ADMIN_PASSWORD`, or `GOLOS_ADMIN_TOKEN` if a separate password is not set

Production checks:

```bash
systemctl status golos-support
curl -fsS http://127.0.0.1:8765/health
curl -fsS https://golos.msgcrm.ru/health
curl -fsS https://golos.msgcrm.ru/api/update
nginx -t
certbot certificates
```

Private diagnostics admin:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli diagnostics --limit 20
./.venv/bin/python -m support_server.cli show REPORT_ID
```

Manual premium MVP:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli premium create --label "Client name" --minutes 180 --amount-rub 100
./.venv/bin/python -m support_server.cli premium list
./.venv/bin/python -m support_server.cli premium grant LICENSE_ID --minutes 180 --amount-rub 100
```

The public landing page is available at `/`.
The HTML admin page is available at `/admin/login` and requires the admin username and password before diagnostics or premium keys are shown.

In-app account and payment MVP:

- desktop app signs in through `/api/account/login`;
- account token can authorize `/api/premium/balance`, `/api/premium/transcribe`, `/api/client/actions`, and diagnostics upload;
- `/api/account/payments` creates a top-up payment;
- default `GOLOS_PAYMENTS_MODE=mock` allows safe local tests;
- YooMoney can be enabled on production through environment variables.

Do not commit server env files, support tokens, diagnostic archives, SQLite data, SSH keys, or production backups.

Минимальный сервер поддержки для проекта "Голос".

## Что умеет

- `GET /health` - проверка, что сервер жив.
- `POST /api/diagnostics` - принимает diagnostic ZIP от приложения.
- `POST /api/events` - принимает технические события.
- `GET /api/update` - отдаёт `latest.json` из локального файла или проксирует публичный GitHub Release.
- `POST /api/account/register` - создаёт аккаунт клиента и внутреннюю премиум-лицензию.
- `POST /api/account/login` - выдаёт сессионный токен для приложения.
- `GET /api/account/me` - возвращает профиль и баланс.
- `POST /api/account/payments` - создаёт платёж на пополнение минут.
- `POST /payments/yoomoney/webhook` - принимает подтверждение оплаты YooMoney.
- `GET /api/premium/balance` - проверяет премиум-ключ и баланс минут.
- `POST /api/premium/transcribe` - распознаёт WAV через серверный OpenAI API и списывает секунды.
- `POST /api/server/transcribe` - распознаёт WAV локальной серверной моделью без OpenAI и без списания премиум-минут.
- `GET /api/client/actions` - отдаёт безопасные запросы поддержки клиенту.
- `POST /api/client/actions/{action_id}/complete` - закрывает запрос поддержки после действия пользователя.

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
- `OPENAI_API_KEY` - серверный ключ OpenAI для премиум-распознавания; не нужен обычному клиенту.
- `GOLOS_PREMIUM_TRANSCRIBE_MODEL` - модель OpenAI для премиум-распознавания, по умолчанию `gpt-4o-mini-transcribe`.
- `GOLOS_PUBLIC_APP_URL` - публичный адрес сервера, по умолчанию `https://golos.msgcrm.ru`.
- `GOLOS_PAYMENTS_MODE` - `mock` для тестов или боевой режим провайдера, по умолчанию `mock`.
- `GOLOS_PAYMENTS_PROVIDER` - провайдер платежей, сейчас `yoomoney`.
- `GOLOS_PAYMENT_DEFAULT_AMOUNT_RUB` - сумма пополнения по умолчанию, сейчас `100`.
- `GOLOS_PAYMENT_MIN_AMOUNT_RUB` / `GOLOS_PAYMENT_MAX_AMOUNT_RUB` - допустимый диапазон пополнения.
- `GOLOS_PREMIUM_MINUTES_PER_100_RUB` - сколько минут начислять за 100 рублей, сейчас `180`.
- `GOLOS_YOOMONEY_RECEIVER` - получатель YooMoney.
- `GOLOS_YOOMONEY_NOTIFICATION_SECRET` - секрет проверки webhook YooMoney.
- `GOLOS_STT_ENABLED` - включает локальное серверное распознавание на `/api/server/transcribe`, по умолчанию `false`.
- `GOLOS_STT_MODEL_SIZE` - модель `faster-whisper` для серверного режима, по умолчанию `base`.
- `GOLOS_STT_DEVICE` - устройство для серверной модели, обычно `cpu` или `cuda`, по умолчанию `cpu`.
- `GOLOS_STT_COMPUTE_TYPE` - тип вычислений, по умолчанию `int8`.
- `GOLOS_STT_BEAM_SIZE` - beam size для серверной модели, по умолчанию `1`.
- `GOLOS_STT_VAD_FILTER` - включает VAD-фильтр, по умолчанию `true`.
- `GOLOS_STT_MAX_DURATION_SECONDS` - максимальная длительность одного аудио для серверного режима, по умолчанию `120`.
- `GOLOS_STT_RATE_LIMIT_PER_MINUTE` - простой лимит запросов на IP для `/api/server/transcribe`, по умолчанию `30`.

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

Для нового премиум-режима приложение хранит сессионный токен аккаунта локально в `.env`:

```text
GOLOS_ACCOUNT_EMAIL=...
GOLOS_ACCOUNT_TOKEN=...
```

Старый ручной вариант с премиум-ключом остаётся для совместимости:

```text
GOLOS_PREMIUM_KEY=...
```

Аккаунт-токен или премиум-ключ используется для `/api/premium/balance`, `/api/premium/transcribe`, безопасных client actions и загрузки диагностики без выдачи пользователю служебного `GOLOS_SUPPORT_TOKEN`.

Для бесплатного серверного режима приложение использует `/api/server/transcribe`. Этот endpoint не требует пользовательского OpenAI-ключа и не использует серверный OpenAI API, но требует включённого `GOLOS_STT_ENABLED=1` на сервере.

## Безопасность

Сервер отвергает diagnostic ZIP, если внутри есть `.env`, временное аудио, папки `temp/` или `models/`.
Сам OpenAI API key не должен отправляться ни в архиве, ни отдельным полем.
Удалённые действия ограничены безопасными запросами: попросить диагностику или предложить обновление. Сервер не умеет запускать команды Windows, читать произвольные файлы или включать микрофон.
