from __future__ import annotations

import hashlib
import json
import re
import secrets
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


@dataclass(slots=True)
class DiagnosticReport:
    report_id: str
    created_at: str
    installation_id: str
    app_version: str
    profile: str
    backend: str
    platform: str
    original_filename: str
    stored_path: Path
    size_bytes: int
    sha256: str
    notes: str


@dataclass(slots=True)
class PremiumLicense:
    license_id: str
    key_prefix: str
    created_at: str
    updated_at: str
    label: str
    notes: str
    active: bool
    balance_seconds: int
    total_granted_seconds: int
    total_used_seconds: int
    total_amount_rub: int
    last_seen_at: str


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
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS premium_licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_id TEXT NOT NULL UNIQUE,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    balance_seconds INTEGER NOT NULL,
                    total_granted_seconds INTEGER NOT NULL,
                    total_used_seconds INTEGER NOT NULL,
                    total_amount_rub INTEGER NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS premium_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT NOT NULL UNIQUE,
                    license_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    seconds_delta INTEGER NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    FOREIGN KEY (license_id) REFERENCES premium_licenses (license_id)
                )
                """
            )


def diagnostics_dir(settings: ServerSettings) -> Path:
    return settings.data_dir / "diagnostics"


def list_diagnostic_reports(settings: ServerSettings, limit: int = 50) -> list[DiagnosticReport]:
    limit = max(1, min(limit, 200))
    with closing(_connect(settings)) as db:
        rows = db.execute(
            """
            SELECT report_id, created_at, installation_id, app_version, profile, backend,
                   platform, original_filename, stored_path, size_bytes, sha256, notes
            FROM diagnostic_reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_diagnostic_report_from_row(row) for row in rows]


def get_diagnostic_report(settings: ServerSettings, report_id: str) -> DiagnosticReport | None:
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT report_id, created_at, installation_id, app_version, profile, backend,
                   platform, original_filename, stored_path, size_bytes, sha256, notes
            FROM diagnostic_reports
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()
    if row is None:
        return None
    return _diagnostic_report_from_row(row)


def create_premium_license(
    settings: ServerSettings,
    label: str,
    minutes: int,
    amount_rub: int = 0,
    notes: str = "",
) -> tuple[str, PremiumLicense]:
    minutes = max(0, int(minutes))
    amount_rub = max(0, int(amount_rub))
    license_key = _new_premium_key()
    license_id = uuid4().hex
    created_at = _utc_now()
    seconds = minutes * 60
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO premium_licenses (
                    license_id, key_hash, key_prefix, created_at, updated_at, label, notes,
                    active, balance_seconds, total_granted_seconds, total_used_seconds,
                    total_amount_rub, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0, ?, '')
                """,
                (
                    license_id,
                    premium_key_hash(license_key),
                    license_key[:14],
                    created_at,
                    created_at,
                    label.strip(),
                    notes.strip(),
                    seconds,
                    seconds,
                    amount_rub,
                ),
            )
            _insert_premium_ledger(db, license_id, "create", seconds, amount_rub, notes.strip())
    license = get_premium_license(settings, license_id)
    if license is None:
        raise RuntimeError("Premium license was not created.")
    return license_key, license


def list_premium_licenses(settings: ServerSettings, limit: int = 50) -> list[PremiumLicense]:
    limit = max(1, min(limit, 200))
    with closing(_connect(settings)) as db:
        rows = db.execute(
            """
            SELECT license_id, key_prefix, created_at, updated_at, label, notes, active,
                   balance_seconds, total_granted_seconds, total_used_seconds,
                   total_amount_rub, last_seen_at
            FROM premium_licenses
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_premium_license_from_row(row) for row in rows]


def get_premium_license(settings: ServerSettings, identifier: str) -> PremiumLicense | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    where = "license_id = ?"
    value = identifier
    if identifier.startswith("golos_"):
        where = "key_hash = ?"
        value = premium_key_hash(identifier)
    with closing(_connect(settings)) as db:
        row = db.execute(
            f"""
            SELECT license_id, key_prefix, created_at, updated_at, label, notes, active,
                   balance_seconds, total_granted_seconds, total_used_seconds,
                   total_amount_rub, last_seen_at
            FROM premium_licenses
            WHERE {where}
            """,
            (value,),
        ).fetchone()
    if row is None:
        return None
    return _premium_license_from_row(row)


def grant_premium_minutes(
    settings: ServerSettings,
    identifier: str,
    minutes: int,
    amount_rub: int = 0,
    notes: str = "",
) -> PremiumLicense:
    license = get_premium_license(settings, identifier)
    if license is None:
        raise ValueError("Premium license not found.")
    seconds = max(0, int(minutes)) * 60
    amount_rub = max(0, int(amount_rub))
    updated_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE premium_licenses
                SET updated_at = ?,
                    balance_seconds = balance_seconds + ?,
                    total_granted_seconds = total_granted_seconds + ?,
                    total_amount_rub = total_amount_rub + ?
                WHERE license_id = ?
                """,
                (updated_at, seconds, seconds, amount_rub, license.license_id),
            )
            _insert_premium_ledger(db, license.license_id, "grant", seconds, amount_rub, notes.strip())
    updated = get_premium_license(settings, license.license_id)
    if updated is None:
        raise RuntimeError("Premium license disappeared after grant.")
    return updated


def set_premium_license_active(settings: ServerSettings, identifier: str, active: bool) -> PremiumLicense:
    license = get_premium_license(settings, identifier)
    if license is None:
        raise ValueError("Premium license not found.")
    updated_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE premium_licenses
                SET updated_at = ?, active = ?
                WHERE license_id = ?
                """,
                (updated_at, 1 if active else 0, license.license_id),
            )
            _insert_premium_ledger(db, license.license_id, "activate" if active else "deactivate", 0, 0, "")
    updated = get_premium_license(settings, license.license_id)
    if updated is None:
        raise RuntimeError("Premium license disappeared after status change.")
    return updated


def touch_premium_license(settings: ServerSettings, license_key: str) -> PremiumLicense | None:
    license = get_premium_license(settings, license_key)
    if license is None:
        return None
    seen_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE premium_licenses
                SET last_seen_at = ?
                WHERE license_id = ?
                """,
                (seen_at, license.license_id),
            )
    return get_premium_license(settings, license.license_id)


def premium_key_hash(license_key: str) -> str:
    return hashlib.sha256(license_key.strip().encode("utf-8")).hexdigest()


def resolve_report_archive(settings: ServerSettings, report: DiagnosticReport) -> Path:
    archive_path = report.stored_path.resolve()
    root = diagnostics_dir(settings).resolve()
    try:
        archive_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Diagnostic archive path is outside diagnostics directory.") from exc
    if not archive_path.is_file():
        raise FileNotFoundError(str(archive_path))
    return archive_path


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


def _diagnostic_report_from_row(row: tuple[object, ...]) -> DiagnosticReport:
    return DiagnosticReport(
        report_id=str(row[0]),
        created_at=str(row[1]),
        installation_id=str(row[2]),
        app_version=str(row[3]),
        profile=str(row[4]),
        backend=str(row[5]),
        platform=str(row[6]),
        original_filename=str(row[7]),
        stored_path=Path(str(row[8])),
        size_bytes=int(row[9]),
        sha256=str(row[10]),
        notes=str(row[11]),
    )


def _premium_license_from_row(row: tuple[object, ...]) -> PremiumLicense:
    return PremiumLicense(
        license_id=str(row[0]),
        key_prefix=str(row[1]),
        created_at=str(row[2]),
        updated_at=str(row[3]),
        label=str(row[4]),
        notes=str(row[5]),
        active=bool(row[6]),
        balance_seconds=int(row[7]),
        total_granted_seconds=int(row[8]),
        total_used_seconds=int(row[9]),
        total_amount_rub=int(row[10]),
        last_seen_at=str(row[11]),
    )


def _insert_premium_ledger(
    db: sqlite3.Connection,
    license_id: str,
    entry_type: str,
    seconds_delta: int,
    amount_rub: int,
    note: str,
) -> None:
    db.execute(
        """
        INSERT INTO premium_ledger (
            entry_id, license_id, created_at, entry_type, seconds_delta, amount_rub, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (uuid4().hex, license_id, _utc_now(), entry_type, seconds_delta, amount_rub, note),
    )


def _new_premium_key() -> str:
    return f"golos_{secrets.token_urlsafe(24)}"


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
