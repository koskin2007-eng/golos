# Project structure

```text
Голос
├─ AGENTS.md
├─ README.md
├─ config.yaml
├─ requirements.txt
├─ run.ps1
├─ build_exe.ps1
├─ package_release.ps1
├─ support_server/
│  ├─ main.py
│  ├─ settings.py
│  ├─ storage.py
│  ├─ yoomoney.py
│  ├─ requirements.txt
│  └─ run_local.ps1
├─ docs/
│  ├─ PROJECT_STRUCTURE.md
│  ├─ REMOTE_RELEASE_SUPPORT_PLAN.md
│  ├─ ROADMAP.md
│  └─ ui-mockup.png
└─ voice_input/
   ├─ app.py
   ├─ account.py
   ├─ config.py
   ├─ diagnostics.py
   ├─ hotkey.py
   ├─ logger.py
   ├─ paste.py
   ├─ paths.py
   ├─ premium.py
   ├─ recorder.py
   ├─ remote_actions.py
   ├─ shortcuts.py
   ├─ single_instance.py
   ├─ settings_window.py
   ├─ support.py
   ├─ tray.py
   ├─ utils.py
   └─ transcribers/
      ├─ faster_whisper_transcriber.py
      ├─ openai_transcriber.py
      └─ premium_proxy_transcriber.py
```

## Root files

- `AGENTS.md` - working rules for Codex and developers.
- `README.md` - user guide: install, run, hotkeys, profiles, diagnostics.
- `config.yaml` - runtime settings: hotkey, language, backend, profiles, paste, logs.
- `requirements.txt` - Python dependencies.
- `run.ps1` - normal development/user launch without EXE rebuild.
- `build_exe.ps1` - PyInstaller release build script.
- `package_release.ps1` - release packager that creates `Golos-win64.zip`, `Golos-win64.sha256`, and `latest.json`.
- `support_server/` - optional FastAPI server for diagnostics, events, update metadata, premium keys, in-app accounts, payments, and safe support actions.

## Docs

- `docs/PROJECT_STRUCTURE.md` - project file map.
- `docs/ROADMAP.md` - short product and technical roadmap.
- `docs/REMOTE_RELEASE_SUPPORT_PLAN.md` - staged plan for GitHub Releases, updates, diagnostics, support server, and OpenAI key modes.
- `docs/ui-mockup.png` - early interface mockup.

## Runtime folders

These folders are local runtime output and are not committed:

- `.venv/` - Python virtual environment.
- `dist/` - built EXE package.
- `build/` - PyInstaller build cache.
- `models/` - downloaded Whisper models.
- `logs/` - application logs.
- `diagnostics/` - diagnostic zip archives.
- `temp/` - temporary WAV recordings.

## Main modules

- `voice_input/app.py` - app entry point, CLI, hotkey lifecycle, record-transcribe-paste pipeline.
- `voice_input/account.py` - desktop account API client, local session token helpers, and top-up request helper.
- `voice_input/config.py` - config loading, defaults, recognition profiles.
- `voice_input/recorder.py` - microphone recording.
- `voice_input/hotkey.py` - global push-to-talk key handling.
- `voice_input/paste.py` - text paste through clipboard and keyboard shortcuts.
- `voice_input/tray.py` - system tray UI.
- `voice_input/settings_window.py` - user-facing settings window.
- `voice_input/shortcuts.py` - Windows Start Menu and Startup shortcut management.
- `voice_input/support.py` - manual GitHub support request and diagnostic package helper.
- `voice_input/premium.py` - premium auth helpers and balance check through either legacy premium key or account token.
- `voice_input/remote_actions.py` - safe support action polling and completion helpers.
- `voice_input/updater.py` - GitHub Release update check, verified package download, extraction, and Windows update installer request.
- `voice_input/version.py` - application version, release tag, and GitHub repository id.
- `voice_input/diagnostics.py` - safe diagnostic zip collection.
- `voice_input/single_instance.py` - Windows mutex to prevent duplicate app instances.
- `voice_input/logger.py` - rotating file and console logs.
- `voice_input/paths.py` - source vs EXE runtime paths.
- `voice_input/utils.py` - transcript cleanup helpers.

## Support server

- `support_server/main.py` - FastAPI entry point with `/health`, account APIs, payment pages, diagnostics, events, update metadata, premium transcription, and admin pages.
- `support_server/settings.py` - environment-based server settings.
- `support_server/storage.py` - SQLite helpers for diagnostics, premium licenses, account sessions, payments, and safe support actions.
- `support_server/yoomoney.py` - YooMoney payment form and webhook validation helpers.
- `support_server/requirements.txt` - server-only Python dependencies.
- `support_server/run_local.ps1` - local server launcher.

## Recognition backends

- `voice_input/transcribers/faster_whisper_transcriber.py` - local `faster-whisper` backend.
- `voice_input/transcribers/openai_transcriber.py` - optional OpenAI audio transcription backend.
- `voice_input/transcribers/premium_proxy_transcriber.py` - Golos premium server transcription backend.

## Development flow

Use Python while the app is actively changing:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app
```

Build EXE only for release or handoff:

```powershell
.\build_exe.ps1
```
