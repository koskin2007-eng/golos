from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

from support_server.settings import ServerSettings
from voice_input.config import LocalWhisperSettings
from voice_input.transcribers import TranscriptionResult
from voice_input.transcribers.faster_whisper_transcriber import FasterWhisperTranscriber


_TRANSCRIBERS: dict[tuple[str, str, str, int, bool, str], FasterWhisperTranscriber] = {}
_TRANSCRIBERS_LOCK = threading.Lock()


def transcribe_with_local_model(
    settings: ServerSettings,
    content: bytes,
    filename: str,
    language: str,
    logger: logging.Logger | None = None,
) -> TranscriptionResult:
    transcriber = _get_transcriber(settings, language, logger)
    suffix = Path(filename).suffix or ".wav"
    temp_dir = settings.data_dir / "stt_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=temp_dir) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        return transcriber.transcribe(temp_path)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _get_transcriber(
    settings: ServerSettings,
    language: str,
    logger: logging.Logger | None,
) -> FasterWhisperTranscriber:
    language = language if language in {"ru", "en", "auto"} else "ru"
    key = (
        settings.stt_model_size,
        settings.stt_device,
        settings.stt_compute_type,
        settings.stt_beam_size,
        settings.stt_vad_filter,
        language,
    )
    with _TRANSCRIBERS_LOCK:
        if key not in _TRANSCRIBERS:
            local_settings = LocalWhisperSettings(
                model_size=settings.stt_model_size,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type,
                beam_size=settings.stt_beam_size,
                vad_filter=settings.stt_vad_filter,
            )
            _TRANSCRIBERS[key] = FasterWhisperTranscriber(
                local_settings,
                language,
                "server_proxy",
                logger,
                download_root=settings.data_dir / "models",
            )
        return _TRANSCRIBERS[key]
