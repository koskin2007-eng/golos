from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    elapsed_ms: float
    backend: str
    model: str

