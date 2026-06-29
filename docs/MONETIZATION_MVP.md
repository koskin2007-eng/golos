# Golos Monetization MVP

Account and premium-payment stage for the "Голос" project.

## Product Model

Free:

- local recognition on the user's Windows computer;
- user's own OpenAI API key in local settings;
- diagnostics and updates.

Paid:

- "Голос Премиум" through our server;
- the user signs in inside the desktop app instead of entering a technical premium key;
- our server checks the license balance and proxies OpenAI transcription;
- balance is shown to the user in minutes, not tokens.
- payment happens on the payment provider side; Golos does not collect or store card data.

## Starter Tariff

Initial manual tariff:

- price: 100 RUB;
- package: 180 transcription minutes on the economy OpenAI transcription backend;
- internal margin target: keep at least 40% after OpenAI usage, payment fees, support, and server overhead.

The public user-facing unit is "minutes". Token and OpenAI-cost accounting stays internal.

## In-App Workflow

1. User opens settings in the desktop app and goes to `Аккаунт`.
2. User registers or signs in with email and password.
3. The server creates an internal premium license for the account.
4. The app stores only a local account session token in `.env`.
5. User clicks `Пополнить`, the server creates a payment and returns a payment page URL.
6. The payment page redirects to YooMoney or a future provider. Card data is entered only on the provider side.
7. After provider confirmation/webhook, the server grants minutes to the account license.
8. The app checks balance through the account token and can use the premium profile without manual key entry.
9. Support can request diagnostics through a safe client action; the user still confirms before anything is sent.

Telegram is not part of the client flow. Admin Telegram notifications can be added later as an internal operator channel only.

## Automatic Payments

Implemented fast-start server flow:

- `POST /api/account/register` - create account and internal premium license.
- `POST /api/account/login` - issue a local app session token.
- `GET /api/account/me` - show balance and account metadata.
- `POST /api/account/payments` - create a top-up payment.
- `GET /account/payments/{payment_id}` - simple payment status page.
- `GET /account/payments/{payment_id}/yoomoney` - YooMoney handoff page when provider mode is enabled.
- `POST /payments/yoomoney/webhook` - provider confirmation endpoint.

Default local mode is `mock`, so the flow can be tested without real money. Production can switch to YooMoney by setting server env variables.

## Admin CLI

Manual premium keys still exist as an admin fallback and for compatibility.

Create a fallback key:

```bash
cd /opt/golos-support
./.venv/bin/python -m support_server.cli premium create --label "Client name" --minutes 180 --amount-rub 100
```

List keys:

```bash
./.venv/bin/python -m support_server.cli premium list
```

Top up an existing key:

```bash
./.venv/bin/python -m support_server.cli premium grant LICENSE_ID --minutes 180 --amount-rub 100
```

Disable a key:

```bash
./.venv/bin/python -m support_server.cli premium set-active LICENSE_ID --active no
```

## Admin Web

Protected admin page:

```text
https://golos.msgcrm.ru/admin/premium
```

The created license key is shown only once. Store only the hash and a short prefix in SQLite.

## Implemented MVP

- Desktop profile `premium` uses the Golos support server instead of a user OpenAI key.
- Desktop settings include an `Аккаунт` tab with login, registration, balance check, and top-up action.
- Desktop premium requests can authorize by account token; manual `GOLOS_PREMIUM_KEY` remains compatible.
- Server endpoint `POST /api/premium/transcribe` calls OpenAI with the server key and charges seconds from the premium balance.
- Server endpoint `GET /api/premium/balance` shows active status and remaining minutes.
- Premium key or account token can authorize diagnostics upload to `/api/diagnostics`.
- Admin can queue safe client actions: diagnostics request or update suggestion.
- Server has account and payment tables in SQLite.
- Server has mock payment and YooMoney handoff/webhook scaffolding.

## Next Stages

1. Deploy the account/payment code to production after checking env variables.
2. Configure YooMoney receiver and notification secret on the server.
3. Run one real YooMoney payment from the desktop app and verify automatic minute grant.
4. Add email confirmation and password reset; SMS can be added later if a provider is selected.
5. Add receipts/legal documents and public offer text before promotion.
6. Add rate limits and anti-abuse rules before public promotion.
