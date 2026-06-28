from __future__ import annotations

import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from voice_input.paths import resolve_runtime_path, runtime_base_dir
from voice_input.version import APP_VERSION


SECRET_LINE_RE = re.compile(r"^(\s*(?:api[_-]?key|token|secret|password)\s*[:=]\s*).*$", re.IGNORECASE)
MAX_LOG_BYTES = 5 * 1024 * 1024


def collect_diagnostics(
    config_path: str | Path,
    log_path: str | Path,
    output_dir: str | Path = "diagnostics",
) -> Path:
    diagnostics_dir = resolve_runtime_path(output_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = diagnostics_dir / f"voice_input_diagnostics_{stamp}.zip"

    config = Path(config_path).resolve()
    log = Path(log_path).resolve()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("runtime_info.txt", _runtime_info(config, log))
        if config.exists():
            archive.writestr("config_sanitized.yaml", _sanitize_text(config.read_text(encoding="utf-8", errors="replace")))

        log_dir = log.parent
        if log_dir.exists():
            for path in sorted(log_dir.glob("*.log*")):
                if path.is_file():
                    archive.writestr(f"logs/{path.name}", _read_limited(path))

    return archive_path


def _runtime_info(config_path: Path, log_path: Path) -> str:
    return "\n".join(
        [
            f"created_at={datetime.now().isoformat(timespec='seconds')}",
            f"app_version={APP_VERSION}",
            f"platform={platform.platform()}",
            f"python={sys.version.replace(chr(10), ' ')}",
            f"executable={sys.executable}",
            f"base_dir={runtime_base_dir()}",
            f"config_path={config_path}",
            f"log_path={log_path}",
            "privacy=archive contains logs, sanitized config, and runtime metadata only",
            "",
        ]
    )


def _sanitize_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(SECRET_LINE_RE.sub(r"\1<redacted>", line))
    return "\n".join(lines) + "\n"


def _read_limited(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_LOG_BYTES:
        data = data[-MAX_LOG_BYTES:]
    return data.decode("utf-8", errors="replace")
