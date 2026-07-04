from __future__ import annotations

import json
import logging
import time
import urllib.request
import wave
from pathlib import Path
from uuid import uuid4

from voice_input.config import ServerSTTSettings
from voice_input.transcribers import TranscriptionResult


class ServerProxyTranscriber:
    def __init__(
        self,
        settings: ServerSTTSettings,
        language: str,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.language = language
        self.logger = logger or logging.getLogger(__name__)

    def transcribe(self, wav_path: str | Path) -> TranscriptionResult:
        server_url = self.settings.server_url.strip()
        if not server_url:
            raise RuntimeError("Адрес сервера Голос не указан.")

        path = Path(wav_path)
        duration_seconds = _wav_duration_seconds(path)
        fields = {
            "language": self.language,
            "duration_seconds": f"{duration_seconds:.3f}",
            "model": self.settings.model,
        }
        body, content_type = _multipart_body(fields, "file", path)
        request = urllib.request.Request(
            server_url.rstrip("/") + "/api/server/transcribe",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )

        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        server_elapsed = float(payload.get("elapsed_ms", 0.0) or 0.0)
        return TranscriptionResult(
            text=str(payload.get("text", "")),
            elapsed_ms=server_elapsed or elapsed_ms,
            backend="server_proxy",
            model=str(payload.get("model", self.settings.model)),
        )


def _wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate() or 1
            return audio.getnframes() / rate
    except Exception:  # noqa: BLE001
        return 0.0


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----GolosServerBoundary{uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode("utf-8"),
            b"Content-Type: audio/wav\r\n\r\n",
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
