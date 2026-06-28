from __future__ import annotations

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import logging
import os
import threading
import time
from pathlib import Path

from voice_input.config import AppConfig, ConfigManager
from voice_input.diagnostics import collect_diagnostics
from voice_input.logger import DEFAULT_LOG_PATH, setup_logging
from voice_input.hotkey import PushToTalkHotkey
from voice_input.paste import TextPaster
from voice_input.paths import resolve_runtime_path
from voice_input.recorder import AudioRecorder, RecordingResult
from voice_input.shortcuts import install_shortcuts, remove_shortcuts, shortcut_status, sync_shortcuts
from voice_input.single_instance import SingleInstanceGuard
from voice_input.settings_window import open_settings_window
from voice_input.support import create_support_package, open_support_package
from voice_input.text_corrector import OpenAITextCorrector
from voice_input.tray import TrayController
from voice_input.transcribers.faster_whisper_transcriber import FasterWhisperTranscriber
from voice_input.transcribers.openai_transcriber import OpenAITranscriber
from voice_input.updater import check_for_update
from voice_input.utils import clean_transcript
from voice_input.version import APP_NAME, APP_VERSION


def load_dotenv_file() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        return


class VoiceInputApp:
    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load()
        self.log_path = resolve_runtime_path(DEFAULT_LOG_PATH)
        self.logger = setup_logging(self.config.logs.level, self.log_path)
        self.recorder = AudioRecorder(self.config.audio, logger=self.logger)
        self.paster = TextPaster(self.config.paste, logger=self.logger)
        self.hotkey: PushToTalkHotkey | None = None
        self.tray: TrayController | None = None
        self._transcribers: dict[tuple[str, str, str, str], object] = {}
        self._text_corrector: OpenAITextCorrector | None = None
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._recording = False
        self._processing = False
        self._status = "запуск"

    def run(self, no_tray: bool = False) -> None:
        self._load_dotenv()
        self.logger.info(
            "Application started backend=%s profile=%s hotkey=%s language=%s",
            self.config.backend,
            self.config.recognition_profile,
            self.config.hotkey,
            self.config.language,
        )
        self.logger.info("Application version=%s", APP_VERSION)
        self._log_backend_settings()
        self._sync_windows_shortcuts()
        self.recorder.log_input_device_info()

        if not no_tray:
            self.tray = TrayController(
                config_path=self.config_manager.path,
                log_path=self.log_path,
                status_getter=self.get_status,
                on_exit=self.shutdown,
                diagnostics_collector=self.collect_diagnostics,
                support_request_creator=self.prepare_support_request,
                settings_opener=self.open_settings,
            )

        self.hotkey = PushToTalkHotkey(
            self.config.hotkey,
            on_pressed=self._on_hotkey_pressed,
            on_released=self._on_hotkey_released,
            logger=self.logger,
        )

        self.set_status("готов")
        self.hotkey.start()
        if self.config.performance.preload_model:
            self._preload_local_backend()
        else:
            self.logger.info("Model preload disabled; model will load after first recording")

        try:
            if no_tray:
                self._run_console_loop()
            else:
                assert self.tray is not None
                self.tray.run()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.set_status("остановлено")
        self.logger.info("Application stopped")

    def get_status(self) -> str:
        with self._state_lock:
            return self._status

    def set_status(self, status: str) -> None:
        with self._state_lock:
            self._status = status
        if self.tray is not None:
            self.tray.update_menu()

    def _load_dotenv(self) -> None:
        load_dotenv_file()

    def _log_backend_settings(self) -> None:
        backend = self.config.backend
        if backend == "local_fast":
            settings = self.config.local_fast
            self.logger.info("Backend selected backend=local_fast model=%s device=%s", settings.model_size, settings.device)
        elif backend == "local_quality":
            settings = self.config.local_quality
            self.logger.info(
                "Backend selected backend=local_quality model=%s device=%s",
                settings.model_size,
                settings.device,
            )
        elif backend == "openai":
            self.logger.info("Backend selected backend=openai model=%s api_key_present=%s", self.config.openai.model, bool(os.getenv("OPENAI_API_KEY")))
        else:
            self.logger.warning("Unknown backend in config backend=%s", backend)

    def _sync_windows_shortcuts(self) -> None:
        try:
            status = sync_shortcuts(self.config_manager.path, self.config.startup.run_on_windows_startup)
            self.logger.info(
                "Windows shortcuts synced start_menu=%s startup=%s",
                status.start_menu_exists,
                status.startup_exists,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not sync Windows shortcuts: %s", exc)

    def _preload_local_backend(self) -> None:
        if self.config.backend not in {"local_fast", "local_quality"}:
            return

        def worker() -> None:
            try:
                transcriber = self._get_transcriber(self.config.backend)
                warmup = getattr(transcriber, "warmup", None)
                if warmup is not None:
                    warmup()
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Could not preload local model: %s", exc)

        threading.Thread(target=worker, name="model-preload", daemon=True).start()

    def _on_hotkey_pressed(self) -> None:
        with self._state_lock:
            if self._recording or self._processing:
                return
            self._recording = True

        try:
            self.set_status("запись")
            self._beep(900)
            self.recorder.start()
            self.logger.info("Recording started")
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._recording = False
            self.set_status("ошибка записи")
            self.logger.exception("Recording start failed")
            self._notify("Голос: ошибка", str(exc))

    def _on_hotkey_released(self) -> None:
        with self._state_lock:
            if not self._recording:
                return
            self._recording = False
            self._processing = True

        release_started = time.perf_counter()
        try:
            recording = self.recorder.stop()
            self._beep(600)
            self.logger.info(
                "Recording stopped record_seconds=%.2f frames=%s wav=%s",
                recording.duration_seconds,
                recording.frame_count,
                recording.wav_path,
            )
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._processing = False
            self.set_status("ошибка записи")
            self.logger.exception("Recording stop failed")
            self._notify("Голос: ошибка", str(exc))
            return

        threading.Thread(
            target=self._process_recording,
            args=(recording, release_started),
            name="transcribe-and-paste",
            daemon=True,
        ).start()

    def _process_recording(self, recording: RecordingResult, release_started: float) -> None:
        paste_ms = 0.0
        transcribe_ms = 0.0
        correction_ms = 0.0
        backend_used = self.config.backend
        try:
            self.set_status("распознавание")
            transcriber = self._get_transcriber_for_current_config()
            result = transcriber.transcribe(recording.wav_path)
            backend_used = result.backend
            transcribe_ms = result.elapsed_ms
            text = clean_transcript(result.text)

            if not text:
                self.logger.info(
                    "Empty transcription record_seconds=%.2f transcribe_ms=%.0f backend=%s",
                    recording.duration_seconds,
                    transcribe_ms,
                    backend_used,
                )
                self.set_status("готов")
                return

            text, correction_ms = self._correct_text_if_needed(text)

            self.set_status("вставка")
            paste_ms = self.paster.paste(text)
            total_ms = (time.perf_counter() - release_started) * 1000.0
            self.logger.info(
                "record_seconds=%.2f transcribe_ms=%.0f correction_ms=%.0f paste_ms=%.0f total_ms=%.0f backend=%s text_len=%s",
                recording.duration_seconds,
                transcribe_ms,
                correction_ms,
                paste_ms,
                total_ms,
                backend_used,
                len(text),
            )
            self.set_status("готов")
        except Exception as exc:  # noqa: BLE001
            self.set_status("ошибка")
            self.logger.exception("Transcribe or paste failed")
            self._notify("Голос: ошибка", str(exc))
        finally:
            with self._state_lock:
                self._processing = False

    def _get_transcriber_for_current_config(self):  # noqa: ANN202
        backend = self.config.backend
        if backend == "openai" and not OpenAITranscriber.has_api_key():
            self.logger.error("OPENAI_API_KEY is not set; falling back to local_fast")
            self._notify("Голос", "OPENAI_API_KEY не найден. Использую local_fast.")
            backend = "local_fast"
        return self._get_transcriber(backend)

    def _correct_text_if_needed(self, text: str) -> tuple[str, float]:
        if not self.config.text_correction.enabled:
            return text, 0.0
        if not OpenAITextCorrector.has_api_key():
            self.logger.error("OPENAI_API_KEY is not set; text correction skipped")
            self._notify("Голос", "OPENAI_API_KEY не найден. Исправление текста пропущено.")
            return text, 0.0

        try:
            self.set_status("исправление")
            corrector = self._get_text_corrector()
            result = corrector.correct(text)
            self.logger.info("Text correction done correction_ms=%.0f model=%s text_len=%s", result.elapsed_ms, result.model, len(result.text))
            return clean_transcript(result.text), result.elapsed_ms
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Text correction failed; using original transcription")
            self._notify("Голос: ошибка", f"Не удалось исправить текст через GPT: {exc}")
            return text, 0.0

    def _get_text_corrector(self) -> OpenAITextCorrector:
        if self._text_corrector is None:
            self._text_corrector = OpenAITextCorrector(self.config.text_correction, self.config.language, self.logger)
        return self._text_corrector

    def _get_transcriber(self, backend: str):  # noqa: ANN202
        if backend == "local_fast":
            settings = self.config.local_fast
            key = (backend, settings.model_size, settings.device, settings.compute_type)
            if key not in self._transcribers:
                self._transcribers[key] = FasterWhisperTranscriber(settings, self.config.language, backend, self.logger)
            return self._transcribers[key]

        if backend == "local_quality":
            settings = self.config.local_quality
            key = (backend, settings.model_size, settings.device, settings.compute_type)
            if key not in self._transcribers:
                self._transcribers[key] = FasterWhisperTranscriber(settings, self.config.language, backend, self.logger)
            return self._transcribers[key]

        if backend == "openai":
            key = (backend, self.config.openai.model, "api", self.config.openai.response_format)
            if key not in self._transcribers:
                self._transcribers[key] = OpenAITranscriber(self.config.openai, self.config.language, self.logger)
            return self._transcribers[key]

        raise ValueError(f"Unknown backend: {backend}")

    def _notify(self, title: str, message: str) -> None:
        if self.tray is not None:
            self.tray.notify(title, message)

    def collect_diagnostics(self) -> Path:
        archive_path = collect_diagnostics(self.config_manager.path, self.log_path)
        self.logger.info("Diagnostics collected path=%s", archive_path)
        return archive_path

    def prepare_support_request(self) -> Path:
        package = create_support_package(self.config_manager.path, self.log_path)
        self.logger.info("Support request prepared archive=%s issue_body=%s", package.archive_path, package.issue_body_path)
        open_support_package(package)
        return package.archive_path

    def open_settings(self) -> None:
        import subprocess
        import sys

        if getattr(sys, "frozen", False):
            command = [sys.executable, "--settings", "--config", str(self.config_manager.path)]
        else:
            command = [sys.executable, "-m", "voice_input.app", "--settings", "--config", str(self.config_manager.path)]

        subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            close_fds=True,
        )

    def _beep(self, frequency: int) -> None:
        if not self.config.feedback.beep_on_recording:
            return
        try:
            import winsound

            winsound.Beep(frequency, 80)
        except Exception:  # noqa: BLE001
            pass

    def _run_console_loop(self) -> None:
        print(f"Голос запущен. Удерживайте {self.config.hotkey}, чтобы диктовать. Ctrl+C - выход.")
        try:
            while not self._stop_event.wait(0.5):
                pass
        except KeyboardInterrupt:
            self.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Голосовой ввод для Windows с режимом push-to-talk.", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Показать справку и выйти.")
    parser.add_argument("--config", default="config.yaml", help="Путь к config.yaml.")
    parser.add_argument("--no-tray", action="store_true", help="Запустить без иконки в трее.")
    parser.add_argument("--smoke-test", action="store_true", help="Проверить конфиг и логгер без hotkey.")
    parser.add_argument("--list-devices", action="store_true", help="Показать микрофоны, видимые sounddevice.")
    parser.add_argument("--record-test", type=float, default=0.0, help="Записать короткий WAV N секунд и выйти.")
    parser.add_argument("--transcribe-test", default="", help="Распознать существующий WAV текущим backend.")
    parser.add_argument("--paste-test", default="", help="Вставить переданный текст через буфер и Ctrl+V.")
    parser.add_argument("--list-profiles", action="store_true", help="Показать профили распознавания из config.yaml.")
    parser.add_argument("--set-profile", default="", help="Выбрать recognition_profile в config.yaml и выйти.")
    parser.add_argument("--collect-diagnostics", action="store_true", help="Создать zip диагностики и выйти.")
    parser.add_argument("--prepare-support-request", action="store_true", help="Создать диагностику и открыть обращение на GitHub.")
    parser.add_argument("--settings", action="store_true", help="Открыть окно настроек и выйти.")
    parser.add_argument("--check-update", action="store_true", help="Проверить обновления через GitHub Releases.")
    parser.add_argument("--shortcut-status", action="store_true", help="Показать статус ярлыков Windows.")
    parser.add_argument("--install-shortcuts", action="store_true", help="Создать ярлыки в меню Пуск и автозапуске.")
    parser.add_argument("--remove-shortcuts", action="store_true", help="Удалить ярлыки Голос из меню Пуск и автозапуска.")
    parser.add_argument("--version", action="store_true", help="Показать версию и выйти.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        load_dotenv_file()
        if args.version:
            print(f"{APP_NAME} {APP_VERSION}")
            return 0

        if args.check_update:
            result = check_for_update()
            print(result.message)
            print(f"current_version={result.current_version}")
            print(f"latest_version={result.latest_version}")
            print(f"update_available={str(result.update_available).lower()}")
            if result.info is not None:
                print(f"url={result.info.url}")
                print(f"sha256={result.info.sha256}")
            return 0

        config_manager = ConfigManager(args.config)

        if args.shortcut_status:
            status = shortcut_status()
            print(f"start_menu={str(status.start_menu_exists).lower()} path={status.start_menu_path}")
            print(f"startup={str(status.startup_exists).lower()} path={status.startup_path}")
            return 0

        if args.install_shortcuts:
            config_manager.set_startup_enabled(True)
            status = install_shortcuts(config_manager.path, run_on_windows_startup=True)
            print(f"Start menu shortcut: {status.start_menu_path}")
            print(f"Startup shortcut: {status.startup_path}")
            return 0

        if args.remove_shortcuts:
            config_manager.set_startup_enabled(False)
            status = remove_shortcuts()
            print(f"Start menu shortcut removed: {not status.start_menu_exists}")
            print(f"Startup shortcut removed: {not status.startup_exists}")
            return 0

        if args.list_profiles:
            active = config_manager.get_selected_profile()
            for profile in config_manager.list_profiles():
                marker = "*" if profile == active else " "
                print(f"{marker} {profile}")
            return 0

        if args.set_profile:
            config_manager.set_profile(args.set_profile)
            print(f"recognition_profile set to: {args.set_profile}")
            return 0

        if args.settings:
            open_settings_window(args.config)
            return 0

        config = config_manager.load()
        logger = setup_logging(config.logs.level)

        if args.smoke_test:
            logger.info("Smoke test ok config=%s backend=%s hotkey=%s", config_manager.path, config.backend, config.hotkey)
            print(f"Smoke test ok. Config: {config_manager.path}")
            return 0

        if args.collect_diagnostics:
            archive_path = collect_diagnostics(config_manager.path, resolve_runtime_path(DEFAULT_LOG_PATH))
            logger.info("Diagnostics collected path=%s", archive_path)
            print(f"Diagnostics saved: {archive_path}")
            return 0

        if args.prepare_support_request:
            package = create_support_package(config_manager.path, resolve_runtime_path(DEFAULT_LOG_PATH))
            open_support_package(package)
            logger.info("Support request prepared archive=%s issue_body=%s", package.archive_path, package.issue_body_path)
            print(f"Diagnostics saved: {package.archive_path}")
            print(f"Issue text saved: {package.issue_body_path}")
            print(f"GitHub issue URL: {package.issue_url}")
            return 0

        if args.list_devices:
            print(AudioRecorder.list_input_devices())
            return 0

        if args.record_test > 0:
            recorder = AudioRecorder(config.audio, logger=logger)
            print(f"Recording {args.record_test:.1f}s...")
            recorder.start()
            time.sleep(args.record_test)
            result = recorder.stop()
            print(f"WAV saved: {result.wav_path}")
            return 0

        if args.transcribe_test:
            app = VoiceInputApp(args.config)
            transcriber = app._get_transcriber_for_current_config()
            result = transcriber.transcribe(args.transcribe_test)
            text = clean_transcript(result.text)
            print(text)
            logger.info("Transcribe test done backend=%s model=%s text_len=%s", result.backend, result.model, len(text))
            return 0

        if args.paste_test:
            paster = TextPaster(config.paste, logger=logger)
            elapsed_ms = paster.paste(args.paste_test)
            logger.info("Paste test done paste_ms=%.0f text_len=%s", elapsed_ms, len(args.paste_test))
            return 0

        guard = SingleInstanceGuard()
        if not guard.acquire():
            logger.info("Another Golos instance is already running; exiting")
            print("Голос уже запущен.")
            return 0

        try:
            app = VoiceInputApp(args.config)
            app.run(no_tray=args.no_tray)
        finally:
            guard.release()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("voice_input").exception("Fatal error")
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
