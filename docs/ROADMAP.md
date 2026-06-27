# VoiceInput roadmap

## Current interface

The current UI is intentionally small:

- system tray icon;
- status in the tray menu;
- open `config.yaml`;
- open `logs/app.log`;
- collect diagnostics;
- exit.

There is no full settings window yet.

## Next UI step

Add a small Windows settings window with four tabs:

- Main: hotkey, active language, autostart, current status.
- Recognition: profile selection (`tiny`, `base`, `small`), backend, model.
- Diagnostics: open log, collect diagnostics zip, copy version info.
- Updates: current version, update channel, check for update, install update.

## Update strategy

Recommended path: GitHub Releases as the update source.

1. Build `VoiceInput` on the developer machine or in GitHub Actions.
2. Publish a release with:
   - `VoiceInput-win64.zip`;
   - `latest.json`;
   - SHA256 checksum.
3. Installed apps check `latest.json` on a schedule or from a menu command.
4. The app downloads the zip, checks SHA256, closes the old process, replaces files, and restarts.

This keeps updates centralized without needing a custom server.

## Diagnostics strategy

Implemented first:

- tray command `Collect diagnostics`;
- CLI command `--collect-diagnostics`;
- zip output in `diagnostics/`;
- includes logs, sanitized `config.yaml`, and runtime metadata;
- excludes `.env`, temporary audio, downloaded models, and API keys.

Future optional upload:

- manual attach to GitHub issue;
- upload to a private endpoint;
- Telegram bot upload.

Default should stay manual until privacy rules are agreed.

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
