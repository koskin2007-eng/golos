from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter

from voice_input.config import VisionSettings


@dataclass(slots=True)
class VisionTranslationResult:
    source_language: str
    source_text: str
    translated_text: str
    model: str
    elapsed_ms: float


class OpenAIVisionTranslator:
    def __init__(self, settings: VisionSettings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)
        self._client = None

    @staticmethod
    def has_api_key() -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def _get_client(self):  # noqa: ANN202
        if not self.has_api_key():
            raise RuntimeError("Для перевода экрана нужен OpenAI API-ключ. Добавьте его в настройках Голоса.")
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Не установлен пакет openai. Запустите .\\run.ps1.") from exc
        self._client = OpenAI()
        return self._client

    def translate(self, image: Image.Image) -> VisionTranslationResult:
        prepared = _prepare_image(image, self.settings.max_image_dimension)
        encoded = _encode_image(prepared)
        started = time.perf_counter()
        response = self._get_client().responses.create(
            model=self.settings.model,
            reasoning={"effort": _reasoning_effort(self.settings.model)},
            store=False,
            max_output_tokens=1800,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Ты — точный экранный OCR-переводчик. Найди весь читаемый текст на изображении, "
                        "определи основной язык и переведи текст на русский. Сохраняй смысл, абзацы, списки, "
                        "числа, имена и порядок фрагментов. Не описывай изображение и ничего не выдумывай. "
                        "Верни только JSON без Markdown: "
                        '{"source_language":"язык","source_text":"исходный текст",'
                        '"translated_text":"перевод на русский"}. '
                        "Если текста нет, верни пустые source_text и translated_text."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Распознай и переведи выделенную область на русский."},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{encoded}",
                            "detail": self.settings.detail,
                        },
                    ],
                },
            ],
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        raw = str(getattr(response, "output_text", "") or "").strip()
        payload = _parse_result(raw)
        return VisionTranslationResult(
            source_language=str(payload.get("source_language") or "Не определён").strip(),
            source_text=str(payload.get("source_text") or "").strip(),
            translated_text=str(payload.get("translated_text") or "").strip(),
            model=self.settings.model,
            elapsed_ms=elapsed_ms,
        )


def _prepare_image(image: Image.Image, max_dimension: int) -> Image.Image:
    prepared = image.convert("RGB")
    limit = max(512, int(max_dimension))
    if max(prepared.size) > limit:
        prepared.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    elif max(prepared.size) < min(1200, limit):
        scale = min(1200, limit) / max(prepared.size)
        prepared = prepared.resize(
            (max(1, round(prepared.width * scale)), max(1, round(prepared.height * scale))),
            Image.Resampling.LANCZOS,
        )
    prepared = ImageEnhance.Contrast(prepared).enhance(1.08)
    prepared = prepared.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=2))
    return prepared


def _reasoning_effort(model: str) -> str:
    return "none" if model.startswith("gpt-5.6") else "minimal"


def _encode_image(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _parse_result(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Модель вернула ответ в неизвестном формате. Попробуйте выделить область ещё раз.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Модель не вернула результат перевода.")
    return payload
