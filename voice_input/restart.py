from __future__ import annotations

from datetime import datetime
from pathlib import Path

from voice_input.paths import resolve_runtime_path


RESTART_REQUEST_FILE = Path("temp") / "restart.request"


def restart_request_path() -> Path:
    return resolve_runtime_path(RESTART_REQUEST_FILE)


def write_restart_request() -> Path:
    path = restart_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    return path


def clear_restart_request() -> None:
    restart_request_path().unlink(missing_ok=True)
