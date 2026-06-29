# YooMoney production setup

Короткий чек-лист для включения реальных платежей YooMoney в проекте "Голос".

## Что уже готово

- Сервер умеет создавать платеж на 100 рублей.
- После успешного платежа сервер начисляет премиум-минуты на аккаунт.
- Тестовый режим `mock` уже проверен на production.
- Webhook endpoint уже есть:

```text
https://golos.msgcrm.ru/payments/yoomoney/webhook
```

## Что нужно получить в YooMoney

В личном кабинете YooMoney нужно включить HTTP-уведомления и указать:

```text
Notification URL: https://golos.msgcrm.ru/payments/yoomoney/webhook
```

Нужны два значения:

- `receiver` - номер кошелька/получателя YooMoney;
- `notification_secret` - секрет HTTP-уведомлений.

Эти значения нельзя добавлять в Git, документы, скриншоты или чат.

## Production env

Значения хранятся только на сервере в:

```text
/etc/golos-support/golos-support.env
```

Нужно добавить или обновить переменные:

```text
GOLOS_PUBLIC_APP_URL=https://golos.msgcrm.ru
GOLOS_PAYMENTS_MODE=yoomoney
GOLOS_PAYMENTS_PROVIDER=yoomoney
GOLOS_PAYMENT_DEFAULT_AMOUNT_RUB=100
GOLOS_PAYMENT_MIN_AMOUNT_RUB=100
GOLOS_PAYMENT_MAX_AMOUNT_RUB=15000
GOLOS_PREMIUM_MINUTES_PER_100_RUB=180
GOLOS_YOOMONEY_RECEIVER=<secret>
GOLOS_YOOMONEY_NOTIFICATION_SECRET=<secret>
```

Пока `GOLOS_YOOMONEY_RECEIVER` и `GOLOS_YOOMONEY_NOTIFICATION_SECRET` не заданы,
оставляем `GOLOS_PAYMENTS_MODE=mock`, чтобы пользователи не попадали на нерабочую оплату.

## Проверка после включения

1. Создать тестовый аккаунт в программе или через API.
2. Нажать пополнение на 100 рублей.
3. Убедиться, что открывается страница YooMoney.
4. Провести оплату 100 рублей.
5. Проверить, что баланс аккаунта увеличился на 180 минут.
6. Проверить `/admin/payments`, что платеж имеет статус `paid`.

## Ограничение

Текущий сценарий YooMoney - быстрый старт через кошелек и HTTP-уведомления.
Перед широкими продажами нужно отдельно проверить правила YooMoney,
идентификацию кошелька, налоги, оферту и возвраты.
