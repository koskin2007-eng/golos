# AGENTS.md

Правила проекта "Голос" для Codex и разработчиков.

## Стек

- Windows desktop utility.
- Python 3.10+.
- `faster-whisper` for local speech recognition.
- Optional OpenAI transcription backend through `OPENAI_API_KEY`.
- `pynput` for global push-to-talk hotkey.
- `sounddevice` for microphone recording.
- `pystray` + Pillow for tray UI.
- PyInstaller only for release EXE builds.

## Команды разработки

Рабочий запуск во время доработки:

```powershell
.\run.ps1
```

Быстрый запуск без пересборки EXE:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app
```

Проверка конфигурации:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --smoke-test
```

Список профилей распознавания:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --list-profiles
```

Сбор диагностики:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --collect-diagnostics
```

## Сборка EXE

Во время активной разработки EXE не пересобирать без явной причины. Это долго и мешает быстрым итерациям.

Собирать EXE только:

- перед передачей программы другому человеку;
- перед GitHub Release;
- после изменения упаковки, зависимостей или ресурсов, которые надо проверить именно в EXE.

Команда:

```powershell
.\build_exe.ps1
```

## Проверки

После изменений запускать доступные проверки:

```powershell
.\.venv\Scripts\python.exe -m compileall voice_input
.\.venv\Scripts\python.exe -m voice_input.app --smoke-test
.\.venv\Scripts\python.exe -m voice_input.app --list-profiles
```

Для функций диагностики:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --collect-diagnostics
```

## Безопасность

- Не коммитить `.env`, реальные API-ключи, токены, приватные ключи, пароли, VPN-ссылки и другие секреты.
- Не добавлять в диагностический архив `.env`, аудио из `temp/`, модели из `models/`, приватные ключи и токены.
- OpenAI-режим включать явно через конфиг или профиль, чтобы пользователь понимал, что аудио отправляется во внешний API.
- Не менять production/update-поведение без короткого плана.

## Стиль кода

- Вносить минимальные точечные изменения.
- Сохранять текущую архитектуру модулей `voice_input/`.
- Не добавлять новые зависимости без причины.
- Использовать типы и понятные имена.
- Комментарии добавлять только там, где они реально помогают понять код.

## UI и дизайн

- Основное направление интерфейса: чистый Windows-инструмент, но с более радостной зелёно-жёлтой палитрой.
- Цвета: зелёный, жёлтый, белый, тёмный текст, немного синего только для служебных акцентов.
- Не усложнять интерфейс: сначала tray menu, затем небольшое окно настроек.
- Кнопки должны иметь нормальные hover/active-состояния, аккуратную окантовку и не ломаться на длинном русском тексте.

## Git

- Ветки для работы создавать в формате `codex/{feature}`.
- Перед коммитом проверять `git status --short --branch`.
- Не коммитить `dist/`, `build/`, `.venv/`, `models/`, `logs/`, `diagnostics/`, `temp/`.
- После важных изменений синхронизировать ветку с GitHub.
- Если пользователь хочет видеть проект сразу на GitHub, пушить изменения в `main` после проверки.
