from __future__ import annotations

import re
import time
from pathlib import Path


WHITESPACE_RE = re.compile(r"[ \t\f\v]+")


def clean_transcript(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def now_ms() -> float:
    return time.perf_counter() * 1000.0

