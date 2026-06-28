from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from voice_input.paths import resolve_runtime_path
from voice_input.version import APP_VERSION, LATEST_RELEASE_JSON_URL


@dataclass(slots=True)
class UpdateInfo:
    version: str
    tag: str
    asset: str
    sha256: str
    url: str


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    message: str
    info: UpdateInfo | None = None


def check_for_update(url: str = LATEST_RELEASE_JSON_URL, current_version: str = APP_VERSION) -> UpdateCheckResult:
    info = fetch_latest_release(url)
    latest = _version_tuple(info.version)
    current = _version_tuple(current_version)
    update_available = latest > current
    if latest > current:
        message = f"Доступна новая версия {info.version}."
    elif latest < current:
        message = f"Текущая версия {current_version} новее публичного релиза {info.version}."
    else:
        message = f"Установлена актуальная версия {current_version}."
    return UpdateCheckResult(
        current_version=current_version,
        latest_version=info.version,
        update_available=update_available,
        message=message,
        info=info,
    )


def fetch_latest_release(url: str = LATEST_RELEASE_JSON_URL) -> UpdateInfo:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    return UpdateInfo(
        version=str(payload["version"]),
        tag=str(payload["tag"]),
        asset=str(payload["asset"]),
        sha256=str(payload["sha256"]).lower(),
        url=str(payload["url"]),
    )


def download_update(info: UpdateInfo, output_dir: str | Path = "updates") -> Path:
    target_dir = resolve_runtime_path(output_dir) / info.tag
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / info.asset
    temp_path = target_path.with_suffix(target_path.suffix + ".part")

    hasher = hashlib.sha256()
    with urllib.request.urlopen(info.url, timeout=120) as response, temp_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            output.write(chunk)

    actual = hasher.hexdigest().lower()
    if actual != info.sha256:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 не совпал: ожидали {info.sha256}, получили {actual}.")

    if target_path.exists():
        target_path.unlink()
    temp_path.rename(target_path)
    return target_path


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in version.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)
