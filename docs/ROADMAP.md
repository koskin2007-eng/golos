# Голос roadmap

## Current interface

The current UI is intentionally small:

- system tray icon;
- status in the tray menu;
- open user settings window;
- open `logs/app.log`;
- collect diagnostics;
- exit.

The first settings window exists and covers common user settings. It should grow gradually instead of exposing raw YAML to normal users.

## Next UI step

Add a small Windows settings window with four tabs:

- Main: hotkey, active language, autostart, current status.
- Account: email login/register, balance, top-up.
- Recognition: profile selection (`tiny`, `base`, `small`), backend, model.
- Diagnostics: open log, collect diagnostics zip, copy version info.
- Updates: current version, update channel, check for update, install update.

Visual direction:

- warmer green and yellow palette;
- joyful but still readable Windows utility;
- dark text on light surfaces;
- blue only as a small secondary/system accent.

## Update strategy

Recommended path: GitHub Releases as the update source.

1. Build the app on the developer machine or in GitHub Actions.
2. Publish a release with:
   - `Golos-win64.zip`;
   - `latest.json`;
   - SHA256 checksum.
3. Installed apps check `latest.json` on a schedule or from a menu command.
4. The app downloads the zip, checks SHA256, closes the old process, replaces files, and restarts.

This keeps updates centralized without needing a custom server.

Stage 1 release commands:

```powershell
.\package_release.ps1
```

The package script creates `dist/release/vX.Y.Z/Golos-win64.zip`, `Golos-win64.sha256`, and `latest.json`.

Current implementation:

- app version is stored in `voice_input/version.py`;
- settings tab `Обновления` shows the current version;
- CLI command `--check-update` reads public `latest.json`;
- update package download verifies SHA256 before saving to `updates/`.
- settings can download a verified update package, ask the running tray app to close, replace application files with a small PowerShell updater, and restart Golos.

## Windows install/startup shortcuts

Current implementation:

- the app creates a Start Menu shortcut for `Голос`;
- settings can enable or disable launch with Windows;
- CLI command `--install-shortcuts` creates Start Menu and Startup shortcuts;
- CLI command `--shortcut-status` prints the current shortcut state;
- CLI command `--remove-shortcuts` removes app-owned Windows shortcuts.

Detailed staged implementation plan:

```text
docs/REMOTE_RELEASE_SUPPORT_PLAN.md
```

## Diagnostics strategy

Implemented first:

- tray command `Собрать диагностику`;
- tray command `Отправить диагностику`;
- settings field for support server URL;
- CLI command `--collect-diagnostics`;
- CLI command `--prepare-support-request`;
- zip output in `diagnostics/`;
- GitHub Issue draft with diagnostic instructions;
- includes logs, sanitized `config.yaml`, and runtime metadata;
- excludes `.env`, temporary audio, downloaded models, and API keys.

Current optional upload:

- manual attach to GitHub issue;
- upload to support server when `support.server_url` is configured;
- upload by premium key for paid users without sharing the internal support token.

Default should stay manual until privacy rules are agreed.

## Support Server

Current implementation:

- `support_server/` FastAPI app;
- `GET /health`;
- `POST /api/account/register`;
- `POST /api/account/login`;
- `GET /api/account/me`;
- `POST /api/account/payments`;
- `POST /api/diagnostics`;
- `POST /api/events`;
- `GET /api/update`;
- `GET /api/premium/balance`;
- `POST /api/premium/transcribe`;
- `GET /api/client/actions`;
- `POST /api/client/actions/{action_id}/complete`;
- SQLite storage under `support_server/data/`;
- optional Bearer token through `GOLOS_SUPPORT_TOKEN`;
- desktop app can upload diagnostics when `support.server_url` is configured.
- premium profile can transcribe through the server and charge the user's minute balance.
- desktop settings can sign in to an account, show balance, and start a top-up payment.
- account token can authorize premium transcription without manual premium-key entry.
- admin can queue safe support actions, limited to diagnostics request and update suggestion.

## Monetization / Account

Current direction:

- keep local recognition free;
- keep user's own OpenAI key as an advanced local option;
- sell `Голос Премиум` minutes through the in-app account;
- do not collect card data in the desktop app;
- redirect payment to YooMoney first, later to a contracted provider such as T-Bank/YooKassa if needed;
- do not make Telegram part of the client account flow.

Next account steps:

1. Deploy account/payment server code.
2. Configure YooMoney env variables and test a real webhook.
3. Add email confirmation and password reset.
4. Add SMS only after choosing a provider and pricing.
5. Add receipts/legal offer text before public paid launch.

## Browser extension idea

A browser extension is useful only for browser text fields. It will not cover Telegram Desktop, Word, Windows apps, CRM desktop windows, or other native inputs.

The current Windows tray app is a better base. A browser extension can be a later companion, not the main architecture.

## Optimization ideas

- Keep `base` as the default profile.
- Add a first-run setup wizard for microphone and hotkey.
- Add visible recording indicator window.
- Add optional `Ctrl+Alt+Space` hotkey preset.
- Add language presets: Russian, English, auto.
- Add GitHub Release updater.
- Add GitHub Actions build workflow.
- Add signed installer later if the app is shared widely.
