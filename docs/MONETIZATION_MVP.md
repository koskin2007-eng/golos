# Golos Monetization MVP

Manual premium stage for the "Голос" project.

## Product Model

Free:

- local recognition on the user's Windows computer;
- user's own OpenAI API key in local settings;
- diagnostics and updates.

Paid:

- "Голос Премиум" through our server;
- the user enters a Golos premium license key instead of an OpenAI key;
- our server checks the license balance and proxies OpenAI transcription;
- balance is shown to the user in minutes, not tokens.

## Starter Tariff

Initial manual tariff:

- price: 100 RUB;
- package: 180 transcription minutes on the economy OpenAI transcription backend;
- internal margin target: keep at least 40% after OpenAI usage, payment fees, support, and server overhead.

The public user-facing unit is "minutes". Token and OpenAI-cost accounting stays internal.

## Manual Workflow

1. User pays 100 RUB manually.
2. Admin creates a premium key in the server admin page or CLI.
3. Admin sends the key to the user once.
4. User enters the key in the desktop app premium settings.
5. The app checks the balance through the server.
6. Premium transcription requests are charged against the minute balance.
7. Support can request diagnostics through a safe client action; the user still confirms before anything is sent.

## Admin CLI

Create a key:

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
- Desktop settings can save `GOLOS_PREMIUM_KEY` locally and check remaining minutes.
- Server endpoint `POST /api/premium/transcribe` calls OpenAI with the server key and charges seconds from the premium balance.
- Server endpoint `GET /api/premium/balance` shows active status and remaining minutes.
- Premium key can authorize diagnostics upload to `/api/diagnostics`.
- Admin can queue safe client actions: diagnostics request or update suggestion.

## Next Stages

1. Deploy the new server code and set server-side `OPENAI_API_KEY`.
2. Test one real premium transcription on a paid key.
3. Add automatic payments and payment webhook.
4. Add user-visible payment page and receipts/legal documents.
5. Add rate limits and anti-abuse rules before public promotion.
