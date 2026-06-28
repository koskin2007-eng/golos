# Голос

Локальная Windows-программа для личного голосового ввода на русском языке.

Сценарий работы простой: удерживаете горячую клавишу, говорите, отпускаете клавишу, текст распознаётся и вставляется в активное окно через буфер обмена и `Ctrl+V`.

## 1. Что делает программа

- Записывает голос с микрофона только пока удерживается горячая клавиша.
- Распознаёт русский текст локально через `faster-whisper`.
- Вставляет готовый текст в браузер, Telegram, Word, Google Docs, CRM и другие активные окна.
- Работает в фоне и показывает иконку в системном трее.
- Поддерживает резервный OpenAI-режим, но только если явно выбран backend `openai`.

Главный режим по умолчанию: `local_fast`. Он не отправляет аудио в интернет.

## 2. Как установить

Нужен Windows и Python 3.10+.

Откройте PowerShell в папке проекта и выполните:

```powershell
.\run.ps1
```

Скрипт создаст `.venv`, установит зависимости из `requirements.txt` и запустит приложение.

Первый запуск локального распознавания может скачать модель Whisper в папку `models/`. После скачивания локальный режим работает без интернета.

## 3. Как запустить

Основной запуск во время разработки и тестирования:

```powershell
.\run.ps1
```

Запуск из уже подготовленного окружения:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app
```

Запуск без иконки в трее, для отладки в консоли:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --no-tray
```

Проверка старта без hotkey, трея и микрофона:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --smoke-test
```

Проверка обновлений через GitHub Releases:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --check-update
```

Создать ярлык в меню «Пуск» и включить автозапуск Windows:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --install-shortcuts
```

Проверить, есть ли ярлыки Windows:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --shortcut-status
```

Подготовить обращение в поддержку:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --prepare-support-request
```

Команда создаст безопасный diagnostic ZIP, текст обращения и откроет GitHub Issue. ZIP нужно прикрепить к обращению вручную.

Локальный сервер поддержки:

```powershell
.\support_server\run_local.ps1
```

Сервер даёт `/health`, `/api/diagnostics`, `/api/events` и `/api/update`. По умолчанию приложение продолжает открывать GitHub Issue; отправка на сервер включается только если в локальном `config.yaml` задан `support.server_url`.

EXE во время активной доработки не пересобираем. Сборка нужна только перед передачей программы другому человеку или перед GitHub Release.

## 4. Как выбрать микрофон

Посмотреть устройства:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --list-devices
```

В `config.yaml` укажите нужное устройство:

```yaml
audio:
  sample_rate: 16000
  channels: 1
  device: null
```

`device: null` означает микрофон Windows по умолчанию. Если нужен конкретный микрофон, укажите его индекс из списка `--list-devices`.

Для обычной настройки откройте меню трея и выберите `Открыть настройки`. Это откроет окно "Голос" без ручного редактирования `config.yaml`.

## 5. Как поменять горячую клавишу

По умолчанию используется `F8`:

```yaml
hotkey: "F8"
```

Можно указать сочетание:

```yaml
hotkey: "ctrl+alt+space"
```

Горячие клавиши обрабатывает `pynput`: он ловит нажатие и отпускание глобально по Windows и обычно требует меньше обходных решений, чем библиотека `keyboard`.

## 6. Как выбрать локальный режим

Активный профиль выбирается строкой:

```yaml
recognition_profile: "base"
```

Готовые профили:

- `tiny` - самый быстрый, но хуже русский текст.
- `base` - текущий рабочий баланс скорости и качества.
- `small` - точнее в некоторых фразах, но на этом ПК заметно медленнее.
- `openai` - отправляет аудио в OpenAI API и обычно лучше справляется со сложной диктовкой, если задан `OPENAI_API_KEY`.

Переключить профиль командой:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --set-profile base
.\.venv\Scripts\python.exe -m voice_input.app --list-profiles
```

После переключения профиля перезапустите приложение.

Текущий быстрый режим:

```yaml
backend: "local_fast"
recognition_profile: "base"

local_fast:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
  beam_size: 1
  vad_filter: true
```

Если нужно точнее, но медленнее, выберите профиль `small`:

```yaml
recognition_profile: "small"
```

Если нужна максимальная скорость, выберите профиль `tiny`:

```yaml
recognition_profile: "tiny"
```

Если локальное распознавание даёт много ошибок, можно попробовать OpenAI-профиль:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --set-profile openai
```

Для возврата на локальный режим:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --set-profile base
```

Есть два OpenAI-режима:

- `Профиль: openai` - OpenAI сам распознаёт аудио.
- `GPT исправляет ошибки после распознавания` - локальная модель распознаёт аудио, а GPT исправляет текст перед вставкой.

Если нужно точнее:

```yaml
backend: "local_quality"

local_quality:
  model_size: "medium"
  device: "auto"
  compute_type: "auto"
```

`local_quality` использует CUDA, если `ctranslate2` видит NVIDIA CUDA. Иначе автоматически работает на CPU с `int8`.

## 7. Как включить OpenAI-режим

Откройте меню трея, выберите `Открыть настройки`, перейдите на вкладку `Распознавание`.
В поле `OpenAI API-ключ` вставьте свой ключ и нажмите `Сохранить`.
Ключ сохранится локально на этом компьютере в `.env`, сам ключ в окне повторно не показывается.

Затем выберите профиль `OpenAI - через интернет, с помощью GPT` или включите галочку `GPT исправляет ошибки после распознавания`.

Технически это соответствует настройке:

```yaml
recognition_profile: "openai"

openai:
  model: "gpt-4o-mini-transcribe"
  response_format: "text"
```

Можно заменить модель на:

```yaml
openai:
  model: "gpt-4o-transcribe"
```

Если `OPENAI_API_KEY` не найден, OpenAI-режим не запускается, а приложение пробует локальный `local_fast`.
Не добавляйте `.env` в Git. Он уже исключён в `.gitignore`.

## 8. Как собрать EXE

Во время активной разработки этот шаг обычно пропускаем.

```powershell
.\build_exe.ps1
```

Результат будет в:

```text
dist/Golos/
```

Сборка использует PyInstaller. Папки `dist/` и `build/` исключены из Git.

Для подготовки GitHub Release:

```powershell
.\package_release.ps1
```

Скрипт соберёт EXE и подготовит:

```text
dist/release/vX.Y.Z/Golos-win64.zip
dist/release/vX.Y.Z/Golos-win64.sha256
dist/release/vX.Y.Z/latest.json
```

Номер папки соответствует текущей версии из `voice_input/version.py`.

В EXE не зашиваются `.env`, OpenAI API key и локальные пользовательские настройки.

## Структура проекта

Подробная структура лежит в:

```text
docs/PROJECT_STRUCTURE.md
```

План релизов, обновлений, диагностики и будущего сервера поддержки:

```text
docs/REMOTE_RELEASE_SUPPORT_PLAN.md
```

## 9. Как добавить автозапуск Windows

Самый простой вариант:

1. Соберите EXE через `.\build_exe.ps1`.
2. Нажмите `Win+R`.
3. Введите `shell:startup`.
4. Добавьте ярлык на `dist\Golos\Golos.exe`.

Настройка `startup.run_on_windows_startup` пока хранится в конфиге как флаг для будущей автоматизации; запись в реестр MVP не делает.

## 10. Частые проблемы

### Горячая клавиша не работает

- Попробуйте другой hotkey, например `F9` или `ctrl+alt+space`.
- Если активное окно запущено от администратора, запустите "Голос" тоже от администратора.
- Проверьте, что приложение не закрыто в трее.

### Windows требует запуск от администратора

Для обычных окон администратор обычно не нужен. Для приложений, запущенных с повышенными правами, Windows может блокировать глобальные события клавиатуры из обычного процесса.

### Микрофон не найден

Запустите:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --list-devices
```

Проверьте микрофон по умолчанию в настройках Windows и задайте `audio.device` в `config.yaml`.

### Распознавание медленное

- Переключите `local_fast.model_size` с `small` на `base`.
- Оставьте `beam_size: 1`.
- Используйте `compute_type: "int8"` на CPU.
- Закройте тяжёлые приложения.
- Если есть NVIDIA GPU, установите CUDA и попробуйте `local_quality.device: "auto"`.

### Как включить CUDA

Установите NVIDIA-драйвер и CUDA-совместимую сборку зависимостей для `ctranslate2`. Затем:

```yaml
backend: "local_quality"

local_quality:
  device: "auto"
  compute_type: "auto"
```

Если CUDA доступна, приложение выберет `device=cuda` и `compute_type=float16`.

### Приложение запускается и сразу пропадает

В EXE-сборке прогрев модели при старте может быть нестабильным на некоторых Windows-системах. По умолчанию он отключён:

```yaml
performance:
  preload_model: false
```

Первое распознавание будет дольше, зато приложение не должно закрываться сразу после старта.

### Повторный запуск не создаёт вторую иконку

У приложения есть защита от дублей. Если "Голос" уже запущен в трее, новый запуск сразу завершится и напишет в консоль:

```text
Голос уже запущен.
```

Старые "мертвые" иконки Windows может показывать в скрытой области трея до наведения мышкой, но новые процессы появляться не должны.

### Текст не вставляется

- Проверьте, что курсор стоит в поле ввода.
- Попробуйте отключить восстановление буфера:

```yaml
paste:
  restore_clipboard: false
```

- Для некоторых приложений может потребоваться запуск "Голос" от администратора.
- Если вставка не появляется, но в `logs/app.log` есть `text_len`, увеличьте задержку восстановления буфера:

```yaml
paste:
  restore_clipboard: true
  restore_delay_ms: 1200
```

## Диагностика

Логи пишутся в:

```text
logs/app.log
```

В меню трея есть пункт `Собрать диагностику`. Он создаёт zip-архив в папке:

```text
diagnostics/
```

Архив содержит логи, безопасную копию `config.yaml` и техническую информацию о запуске. `.env`, аудио из `temp/`, модели и ключи в архив не добавляются.

То же самое можно сделать командой:

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --collect-diagnostics
```

В логах есть технические параметры, например:

```text
record_seconds=3.2 transcribe_ms=480 paste_ms=80 backend=local_fast
```

Полный распознанный текст и секреты в лог не пишутся.

## Проверочные команды

```powershell
.\.venv\Scripts\python.exe -m voice_input.app --smoke-test
.\.venv\Scripts\python.exe -m voice_input.app --record-test 2
.\.venv\Scripts\python.exe -m voice_input.app --transcribe-test temp\recording_example.wav
.\.venv\Scripts\python.exe -m voice_input.app --paste-test "проверка вставки"
.\.venv\Scripts\python.exe -m voice_input.app --collect-diagnostics
```

Hotkey, трей, микрофон и вставку в реальные приложения нужно проверить вручную на Windows-сессии пользователя.
