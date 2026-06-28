from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import urllib.request
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from support_server.settings import ServerSettings


FORBIDDEN_ZIP_PARTS = {".env", ".env.local"}
FORBIDDEN_ZIP_PREFIXES = ("temp/", "models/")
FORBIDDEN_ZIP_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg")


@dataclass(slots=True)
class DiagnosticRecord:
    report_id: str
    stored_path: Path
    sha256: str
    size_bytes: int


def init_storage(settings: ServerSettings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir(settings).mkdir(parents=True, exist_ok=True)
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostic_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    notes TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    installation_id TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    remote_addr TEXT NOT NULL
                )
                """
            )


def diagnostics_dir(settings: ServerSettings) -> Path:
    return settings.data_dir / "diagnostics"


def save_diagnostic_report(
    settings: ServerSettings,
    content: bytes,
    original_filename: str,
    metadata: dict[str, str],
) -> DiagnosticRecord:
    if len(content) > settings.max_upload_bytes:
        raise ValueError("Diagnostic archive is too large.")

    report_id = uuid4().hex
    created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    safe_name = _safe_filename(original_filename or "diagnostics.zip")
    if not safe_name.lower().endswith(".zip"):
        safe_name += ".zip"
    target_dir = diagnostics_dir(settings) / created_at[:10]
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_path = target_dir / f"{created_at.replace(':', '').replace('-', '')}_{report_id}_{safe_name}"
    stored_path.write_bytes(content)

    try:
        _validate_zip(stored_path)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

    sha256 = hashlib.sha256(content).hexdigest()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO diagnostic_reports (
                    report_id, created_at, installation_id, app_version, profile, backend,
                    platform, original_filename, stored_path, size_bytes, sha256, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    created_at,
                    metadata.get("installation_id", ""),
                    metadata.get("app_version", ""),
                    metadata.get("profile", ""),
                    metadata.get("backend", ""),
                    metadata.get("platform", ""),
                    original_filename,
                    str(stored_path),
                    len(content),
                    sha256,
                    metadata.get("notes", ""),
                ),
            )

    return DiagnosticRecord(report_id=report_id, stored_path=stored_path, sha256=sha256, size_bytes=len(content))


def record_event(settings: ServerSettings, payload: dict[str, object], remote_addr: str) -> str:
    event_id = uuid4().hex
    created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO events (
                    event_id, created_at, installation_id, app_version, event_type, payload_json, remote_addr
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    created_at,
                    str(payload.get("installation_id", "")),
                    str(payload.get("app_version", "")),
                    str(payload.get("event_type", "")),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    remote_addr,
                ),
            )
    return event_id


def load_update_payload(settings: ServerSettings) -> dict[str, object]:
    if settings.update_json_path.exists():
        return json.loads(settings.update_json_path.read_text(encoding="utf-8-sig"))

    with urllib.request.urlopen(settings.public_latest_json_url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _connect(settings: ServerSettings) -> sqlite3.Connection:
    db_path = settings.data_dir / "support.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()

    if not names:
        raise ValueError("Diagnostic archive is empty.")

    for name in names:
        normalized = name.replace("\\", "/").lstrip("/")
        lower = normalized.lower()
        if normalized.startswith("../") or "/../" in normalized:
            raise ValueError("Diagnostic archive contains unsafe paths.")
        if any(part in lower.split("/") for part in FORBIDDEN_ZIP_PARTS):
            raise ValueError("Diagnostic archive contains forbidden secret files.")
        if lower.startswith(FORBIDDEN_ZIP_PREFIXES):
            raise ValueError("Diagnostic archive contains forbidden runtime folders.")
        if lower.endswith(FORBIDDEN_ZIP_SUFFIXES):
            raise ValueError("Diagnostic archive contains audio files.")


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).name).strip("._")
    return safe or "diagnostics.zip"
