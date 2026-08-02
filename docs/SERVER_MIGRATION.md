# Переезд сервера Голос

Цель: перенести `golos-support` на новый VPS без потери аккаунтов, платежей,
диагностики, premium-баланса, обновлений и сайта `golos.msgcrm.ru`.

Документ не содержит секретов. Все реальные токены, пароли, OpenAI API key,
YooMoney secrets, SSH-ключи и архивы базы хранятся только на серверах.

## Что переносим

- FastAPI-приложение `support_server`.
- SQLite и диагностические архивы из `/var/lib/golos-support`.
- Production env из `/etc/golos-support/golos-support.env`.
- systemd unit `golos-support`.
- nginx конфиг для домена.
- Домен `golos.msgcrm.ru` после проверки нового сервера.

## Что не переносим через Git

- `/etc/golos-support/golos-support.env`.
- `support.sqlite3` и любые архивы диагностики.
- backup-архивы `*.tar.gz`.
- приватные ключи SSH.
- значения `OPENAI_API_KEY`, `GOLOS_SUPPORT_TOKEN`, `GOLOS_ADMIN_PASSWORD`,
  `GOLOS_YOOMONEY_NOTIFICATION_SECRET`.

## Целевые пути

```text
/opt/golos-support
/etc/golos-support/golos-support.env
/var/lib/golos-support
/etc/systemd/system/golos-support.service
/etc/nginx/sites-available/golos-support
```

## Этап 1. Подготовить новый сервер

Минимум:

- Ubuntu 22.04/24.04.
- 2 CPU / 4 GB RAM для сайта, диагностики, платежей и OpenAI-прокси.
- Для локального server STT лучше 4 CPU / 8 GB RAM, модель `base`, `cpu`, `int8`.
- Открыты порты `80`, `443`, `22`.
- DNS пока можно не переключать.

На новом сервере:

```bash
apt-get update
apt-get install -y git
git clone --branch codex/server-stt-profile https://github.com/koskin2007-eng/golos.git /opt/golos-support
cd /opt/golos-support
APP_DOMAIN=golos.msgcrm.ru DEPLOY_BRANCH=codex/server-stt-profile bash deploy/scripts/install_support_server.sh
```

После установки заполнить секреты:

```bash
nano /etc/golos-support/golos-support.env
systemctl restart golos-support
bash /opt/golos-support/deploy/scripts/health_check.sh
```

На этом этапе новый сервер может отвечать только по IP/локальному `127.0.0.1`.
Публичный HTTPS проверяем после DNS/certbot.

## Этап 2. Сделать backup старого сервера

На старом сервере:

```bash
cd /opt/golos-support
git pull --ff-only
bash deploy/scripts/backup_data.sh
```

Скрипт создаст архив вида:

```text
/var/backups/golos-support/golos-support-backup-YYYYmmdd-HHMMSS.tar.gz
```

Архив содержит секреты и базу, поэтому передавать его только через защищённый канал:

```bash
scp /var/backups/golos-support/golos-support-backup-YYYYmmdd-HHMMSS.tar.gz root@NEW_SERVER:/root/
scp /var/backups/golos-support/golos-support-backup-YYYYmmdd-HHMMSS.tar.gz.sha256 root@NEW_SERVER:/root/
```

## Этап 3. Восстановить данные на новом сервере

На новом сервере:

```bash
cd /root
sha256sum -c golos-support-backup-YYYYmmdd-HHMMSS.tar.gz.sha256
CONFIRM_RESTORE=yes bash /opt/golos-support/deploy/scripts/restore_data.sh /root/golos-support-backup-YYYYmmdd-HHMMSS.tar.gz
```

Проверки:

```bash
systemctl status golos-support
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/api/update
nginx -t
```

Проверить админку временно можно через SSH tunnel или через домен после DNS.

## Этап 4. Проверить новый сервер до переключения DNS

Если домен ещё указывает на старый сервер, проверить локально:

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/
curl -fsS http://127.0.0.1:8765/api/update
```

Проверить данные:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli diagnostics --limit 5
./.venv/bin/python -m support_server.cli premium list --limit 5
```

Проверить платежи:

```text
/admin/payments
/payments/yoomoney/webhook
```

До DNS-переключения YooMoney webhook остаётся на старом сервере, если URL не менялся
и домен ещё смотрит на старый IP.

## Этап 5. Переключить DNS

1. Уменьшить TTL записи `golos.msgcrm.ru` заранее, например до `300`.
2. Поменять `A` запись на IP нового сервера.
3. Дождаться распространения DNS.
4. Выпустить или обновить сертификат:

```bash
certbot --nginx -d golos.msgcrm.ru
```

5. Проверить снаружи:

```bash
curl -fsS https://golos.msgcrm.ru/health
curl -fsS https://golos.msgcrm.ru/api/update
curl -fsS https://golos.msgcrm.ru/
```

## Этап 6. После переключения

Проверить:

- вход в аккаунт из программы;
- баланс аккаунта;
- `/admin/login`;
- `/admin/diagnostics`;
- `/admin/payments`;
- создание платежа на 100 рублей;
- webhook YooMoney;
- premium transcription;
- server STT, если включён `GOLOS_STT_ENABLED=1`;
- отправку диагностики из приложения.

Логи:

```bash
journalctl -u golos-support -n 100 --no-pager
tail -n 100 /var/log/nginx/golos-support.error.log
```

## Откат

Если новый сервер не прошёл проверки:

1. Вернуть DNS `golos.msgcrm.ru` на старый IP.
2. На старом сервере проверить:

```bash
systemctl restart golos-support
curl -fsS https://golos.msgcrm.ru/health
```

3. Не удалять старый сервер минимум 7 дней после успешного переезда.

## Важное для desktop-приложения

Если домен остаётся `https://golos.msgcrm.ru`, обновление EXE не требуется.
Программа продолжит использовать тот же `server_url`.

Если домен меняется:

- обновить `DEFAULT_ACCOUNT_SERVER_URL` в `voice_input/account.py`;
- обновить `PUBLIC_SITE_URL` в `voice_input/branding.py`;
- обновить default `server_url` в `voice_input/config.py`;
- выпустить новую версию через GitHub Release;
- оставить старый домен как redirect/proxy минимум на переходный период.
