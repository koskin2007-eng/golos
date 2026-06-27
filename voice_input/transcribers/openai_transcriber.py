from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from voice_input.config import OpenAISettings
from voice_input.transcribers import TranscriptionResult


class OpenAITranscriber:
    def __init__(
        self,
        settings: OpenAISettings,
        language: str,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.language = language
        self.logger = logger or logging.getLogger(__name__)
        self._client = None

    @staticmethod
    def has_api_key() -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def _get_client(self):  # noqa: ANN202
        if not self.has_api_key():
            raise RuntimeError("OPENAI_API_KEY is not set. OpenAI backend is disabled.")
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAI transcription. Run .\\run.ps1 first.") from exc

        self._client = OpenAI()
        return self._client

    def transcribe(self, wav_path: str | Path) -> TranscriptionResult:
        client = self._get_client()
        started = time.perf_counter()
        with Path(wav_path).open("rb") as audio_file:
            params = {
                "model": self.settings.model,
                "file": audio_file,
                "response_format": self.settings.response_format,
            }
            if self.language != "auto":
                params["language"] = self.language
            response = client.audio.transcriptions.create(**params)

        if isinstance(response, str):
            text = response
        else:
            text = getattr(response, "text", str(response))

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return TranscriptionResult(
            text=text,
            elapsed_ms=elapsed_ms,
            backend="openai",
            model=self.settings.model,
        )
