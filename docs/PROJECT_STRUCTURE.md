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
├─ docs/
│  ├─ PROJECT_STRUCTURE.md
│  ├─ REMOTE_RELEASE_SUPPORT_PLAN.md
│  ├─ ROADMAP.md
│  └─ ui-mockup.png
└─ voice_input/
   ├─ app.py
   ├─ config.py
   ├─ diagnostics.py
   ├─ hotkey.py
   ├─ logger.py
   ├─ paste.py
   ├─ paths.py
   ├─ recorder.py
   ├─ shortcuts.py
   ├─ single_instance.py
   ├─ settings_window.py
   ├─ tray.py
   ├─ utils.py
   └─ transcribers/
      ├─ faster_whisper_transcriber.py
      └─ openai_transcriber.py
```

## Root files

- `AGENTS.md` - working rules for Codex and developers.
- `README.md` - user guide: install, run, hotkeys, profiles, diagnostics.
- `config.yaml` - runtime settings: hotkey, language, backend, profiles, paste, logs.
- `requirements.txt` - Python dependencies.
- `run.ps1` - normal development/user launch without EXE rebuild.
- `build_exe.ps1` - PyInstaller release build script.
- `package_release.ps1` - release packager that creates `Golos-win64.zip`, `Golos-win64.sha256`, and `latest.json`.

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
- `voice_input/config.py` - config loading, defaults, recognition profiles.
- `voice_input/recorder.py` - microphone recording.
- `voice_input/hotkey.py` - global push-to-talk key handling.
- `voice_input/paste.py` - text paste through clipboard and keyboard shortcuts.
- `voice_input/tray.py` - system tray UI.
- `voice_input/settings_window.py` - user-facing settings window.
- `voice_input/shortcuts.py` - Windows Start Menu and Startup shortcut management.
- `voice_input/updater.py` - GitHub Release update check and verified package download.
- `voice_input/version.py` - application version, release tag, and GitHub repository id.
- `voice_input/diagnostics.py` - safe diagnostic zip collection.
- `voice_input/single_instance.py` - Windows mutex to prevent duplicate app instances.
- `voice_input/logger.py` - rotating file and console logs.
- `voice_input/paths.py` - source vs EXE runtime paths.
- `voice_input/utils.py` - transcript cleanup helpers.

## Recognition backends

- `voice_input/transcribers/faster_whisper_transcriber.py` - local `faster-whisper` backend.
- `voice_input/transcribers/openai_transcriber.py` - optional OpenAI audio transcription backend.

## Development flow

Use Python while the app is actively changing:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app
```

Build EXE only for release or handoff:

```powershell
.\build_exe.ps1
```
