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
- our server checks the license balance and later will proxy OpenAI transcription;
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
6. Later, premium transcription requests are charged against the minute balance.

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

## Next Stages

1. Add desktop UI for entering a Golos premium license key.
2. Add client balance check and display remaining minutes.
3. Add server-side OpenAI transcription proxy.
4. Add usage ledger and minute charging after each transcription.
5. Add automatic payments and payment webhook.
6. Add user-visible payment page and receipts/legal documents.
