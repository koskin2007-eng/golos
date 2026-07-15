from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from voice_input.config import TextCorrectionSettings


@dataclass(slots=True)
class TextCorrectionResult:
    text: str
    elapsed_ms: float
    model: str


class OpenAITextCorrector:
    def __init__(self, settings: TextCorrectionSettings, language: str, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.language = language
        self.logger = logger or logging.getLogger(__name__)
        self._client = None

    @staticmethod
    def has_api_key() -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    @property
    def model(self) -> str:
        return os.getenv("OPENAI_TEXT_MODEL") or self.settings.model

    def _get_client(self):  # noqa: ANN202
        if not self.has_api_key():
            raise RuntimeError("OPENAI_API_KEY is not set. Text correction is disabled.")
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for text correction. Run .\\run.ps1 first.") from exc

        self._client = OpenAI()
        return self._client

    def warmup(self) -> None:
        self._get_client()

    def correct(self, text: str) -> TextCorrectionResult:
        source = text.strip()
        if not source:
            return TextCorrectionResult(text=text, elapsed_ms=0.0, model=self.model)

        started = time.perf_counter()
        client = self._get_client()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Ты исправляешь ошибки распознавания русской диктовки. "
                        "Сохраняй смысл, стиль, язык и порядок мыслей. "
                        "Исправляй очевидные ошибки, пунктуацию и окончания. "
                        "Не добавляй объяснения, Markdown, кавычки или варианты ответа. "
                        "Верни только исправленный текст."
                    ),
                },
                {
                    "role": "user",
                    "content": source,
                },
            ],
        )
        corrected = str(getattr(response, "output_text", "") or "").strip()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not corrected:
            corrected = source
        return TextCorrectionResult(text=corrected, elapsed_ms=elapsed_ms, model=self.model)
