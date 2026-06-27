from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from voice_input.config import LocalWhisperSettings
from voice_input.paths import resolve_runtime_path
from voice_input.transcribers import TranscriptionResult


class FasterWhisperTranscriber:
    def __init__(
        self,
        settings: LocalWhisperSettings,
        language: str,
        backend_name: str,
        logger: logging.Logger | None = None,
        download_root: str | Path = "models",
    ) -> None:
        self.settings = settings
        self.language = language
        self.backend_name = backend_name
        self.logger = logger or logging.getLogger(__name__)
        self.download_root = resolve_runtime_path(download_root)
        self._model = None
        self._load_lock = threading.Lock()
        self.device, self.compute_type = self._resolve_runtime()

    def _resolve_runtime(self) -> tuple[str, str]:
        device = self.settings.device.lower()
        if device == "auto":
            device = "cuda" if self._cuda_available() else "cpu"

        compute_type = self.settings.compute_type.lower()
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        return device, compute_type

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _load_model(self):  # noqa: ANN202
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model

            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper is required for local transcription. Run .\\run.ps1 first.") from exc

            self.download_root.mkdir(parents=True, exist_ok=True)
            self.logger.info(
                "Loading faster-whisper model backend=%s model=%s device=%s compute_type=%s",
                self.backend_name,
                self.settings.model_size,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.settings.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.download_root),
            )
        return self._model

    def warmup(self) -> None:
        self._load_model()

    def transcribe(self, wav_path: str | Path) -> TranscriptionResult:
        model = self._load_model()
        started = time.perf_counter()
        segments, _info = model.transcribe(
            str(wav_path),
            language=self.language,
            beam_size=self.settings.beam_size,
            vad_filter=self.settings.vad_filter,
            condition_on_previous_text=False,
        )
        text = "".join(segment.text for segment in segments)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return TranscriptionResult(
            text=text,
            elapsed_ms=elapsed_ms,
            backend=self.backend_name,
            model=self.settings.model_size,
        )
