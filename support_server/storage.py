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
from datetime import datetime, timedelta
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


@dataclass(slots=True)
class ClientAction:
    action_id: str
    license_id: str
    created_at: str
    updated_at: str
    action_type: str
    status: str
    message: str
    result_message: str


@dataclass(slots=True)
class Account:
    account_id: str
    created_at: str
    updated_at: str
    email: str
    name: str
    premium_license_id: str
    active: bool
    email_confirmed: bool
    last_seen_at: str


@dataclass(slots=True)
class AccountPayment:
    payment_id: str
    account_id: str
    license_id: str
    created_at: str
    updated_at: str
    amount_rub: int
    minutes: int
    currency: str
    status: str
    provider: str
    provider_order_id: str
    provider_payment_id: str
    payment_url: str
    description: str
    error_code: str
    error_message: str
    paid_at: str


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
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS client_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL UNIQUE,
                    license_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    result_message TEXT NOT NULL,
                    FOREIGN KEY (license_id) REFERENCES premium_licenses (license_id)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    premium_license_id TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    email_confirmed INTEGER NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY (premium_license_id) REFERENCES premium_licenses (license_id)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS account_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts (account_id)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS account_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL,
                    license_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    minutes INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_order_id TEXT NOT NULL UNIQUE,
                    provider_payment_id TEXT NOT NULL,
                    payment_url TEXT NOT NULL,
                    description TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    paid_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts (account_id),
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


def charge_premium_seconds(settings: ServerSettings, identifier: str, seconds: int, notes: str = "") -> PremiumLicense:
    license = get_premium_license(settings, identifier)
    if license is None:
        raise ValueError("Premium license not found.")
    seconds = max(1, int(seconds))
    if license.balance_seconds < seconds:
        raise ValueError("Premium license balance is not enough.")

    updated_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            cursor = db.execute(
                """
                UPDATE premium_licenses
                SET updated_at = ?,
                    balance_seconds = balance_seconds - ?,
                    total_used_seconds = total_used_seconds + ?
                WHERE license_id = ? AND balance_seconds >= ?
                """,
                (updated_at, seconds, seconds, license.license_id, seconds),
            )
            if cursor.rowcount != 1:
                raise ValueError("Premium license balance is not enough.")
            _insert_premium_ledger(db, license.license_id, "use", -seconds, 0, notes.strip())
    updated = get_premium_license(settings, license.license_id)
    if updated is None:
        raise RuntimeError("Premium license disappeared after charge.")
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


def create_account(settings: ServerSettings, email: str, password: str, name: str = "") -> tuple[str, Account]:
    normalized_email = normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("Укажите корректный email.")
    if len(password) < 8:
        raise ValueError("Пароль должен быть не короче 8 символов.")

    created_at = _utc_now()
    account_id = uuid4().hex
    license_id = uuid4().hex
    license_key = _new_premium_key()
    display_name = name.strip() or normalized_email.split("@", 1)[0] or "Клиент"

    with closing(_connect(settings)) as db:
        existing = db.execute("SELECT account_id FROM accounts WHERE email = ?", (normalized_email,)).fetchone()
        if existing is not None:
            raise ValueError("Аккаунт с таким email уже существует.")

        with db:
            db.execute(
                """
                INSERT INTO premium_licenses (
                    license_id, key_hash, key_prefix, created_at, updated_at, label, notes,
                    active, balance_seconds, total_granted_seconds, total_used_seconds,
                    total_amount_rub, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 0, 0, 0, '')
                """,
                (
                    license_id,
                    premium_key_hash(license_key),
                    license_key[:14],
                    created_at,
                    created_at,
                    normalized_email,
                    "Создан автоматически для аккаунта Голос.",
                ),
            )
            _insert_premium_ledger(db, license_id, "account_create", 0, 0, "Создан аккаунт")
            db.execute(
                """
                INSERT INTO accounts (
                    account_id, created_at, updated_at, email, name, password_hash,
                    premium_license_id, active, email_confirmed, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, '')
                """,
                (
                    account_id,
                    created_at,
                    created_at,
                    normalized_email,
                    display_name,
                    hash_password(password),
                    license_id,
                ),
            )

    token = create_account_session(settings, account_id)
    account = get_account(settings, account_id)
    if account is None:
        raise RuntimeError("Account was not created.")
    return token, account


def authenticate_account(settings: ServerSettings, email: str, password: str) -> tuple[str, Account] | None:
    normalized_email = normalize_email(email)
    if not normalized_email or not password:
        return None

    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT account_id, password_hash, active
            FROM accounts
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
    if row is None or not bool(row[2]):
        return None
    if not verify_password(password, str(row[1])):
        return None

    token = create_account_session(settings, str(row[0]))
    account = get_account(settings, str(row[0]))
    if account is None:
        return None
    return token, account


def create_account_session(settings: ServerSettings, account_id: str, days: int = 90) -> str:
    token = _new_account_token()
    created_at = _utc_now()
    expires_at = _utc_after(days=days)
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO account_sessions (
                    session_id, account_id, token_hash, created_at, expires_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uuid4().hex, account_id, account_token_hash(token), created_at, expires_at, created_at),
            )
            db.execute(
                """
                UPDATE accounts
                SET last_seen_at = ?
                WHERE account_id = ?
                """,
                (created_at, account_id),
            )
    return token


def get_account(settings: ServerSettings, account_id: str) -> Account | None:
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT account_id, created_at, updated_at, email, name, premium_license_id,
                   active, email_confirmed, last_seen_at
            FROM accounts
            WHERE account_id = ?
            """,
            (account_id.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _account_from_row(row)


def get_account_by_token(settings: ServerSettings, token: str) -> Account | None:
    token = token.strip()
    if not token:
        return None
    now = _utc_now()
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT a.account_id, a.created_at, a.updated_at, a.email, a.name,
                   a.premium_license_id, a.active, a.email_confirmed, a.last_seen_at
            FROM account_sessions s
            JOIN accounts a ON a.account_id = s.account_id
            WHERE s.token_hash = ? AND s.expires_at > ? AND a.active = 1
            """,
            (account_token_hash(token), now),
        ).fetchone()
        if row is None:
            return None
        account = _account_from_row(row)
        with db:
            db.execute(
                """
                UPDATE account_sessions
                SET last_seen_at = ?
                WHERE token_hash = ?
                """,
                (now, account_token_hash(token)),
            )
            db.execute(
                """
                UPDATE accounts
                SET last_seen_at = ?
                WHERE account_id = ?
                """,
                (now, account.account_id),
            )
    return get_account(settings, account.account_id)


def logout_account(settings: ServerSettings, token: str) -> None:
    token = token.strip()
    if not token:
        return
    with closing(_connect(settings)) as db:
        with db:
            db.execute("DELETE FROM account_sessions WHERE token_hash = ?", (account_token_hash(token),))


def resolve_premium_license(
    settings: ServerSettings,
    premium_key: str | None = None,
    account_token: str | None = None,
) -> PremiumLicense | None:
    if premium_key:
        return touch_premium_license(settings, premium_key)
    if account_token:
        account = get_account_by_token(settings, account_token)
        if account is None:
            return None
        license = get_premium_license(settings, account.premium_license_id)
        if license is None:
            return None
        return touch_premium_license_by_id(settings, license.license_id)
    return None


def touch_premium_license_by_id(settings: ServerSettings, license_id: str) -> PremiumLicense | None:
    license = get_premium_license(settings, license_id)
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


def list_pending_client_actions_for_license(settings: ServerSettings, license_id: str, limit: int = 20) -> list[ClientAction]:
    limit = max(1, min(limit, 50))
    with closing(_connect(settings)) as db:
        rows = db.execute(
            """
            SELECT action_id, license_id, created_at, updated_at, action_type, status, message, result_message
            FROM client_actions
            WHERE license_id = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (license_id, limit),
        ).fetchall()
    return [_client_action_from_row(row) for row in rows]


def mark_client_action_for_license(
    settings: ServerSettings,
    action_id: str,
    license_id: str,
    status: str,
    result_message: str = "",
) -> ClientAction:
    action = get_client_action(settings, action_id)
    if action is None or action.license_id != license_id:
        raise ValueError("Client action not found.")
    if status not in {"done", "declined", "error", "seen"}:
        raise ValueError("Unsupported client action status.")

    updated_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE client_actions
                SET updated_at = ?, status = ?, result_message = ?
                WHERE action_id = ? AND license_id = ?
                """,
                (updated_at, status, result_message.strip()[:1000], action.action_id, license_id),
            )
    updated = get_client_action(settings, action.action_id)
    if updated is None:
        raise RuntimeError("Client action disappeared after update.")
    return updated


def create_account_payment(
    settings: ServerSettings,
    account: Account,
    amount_rub: int,
    minutes: int,
    provider: str,
    description: str = "",
) -> AccountPayment:
    amount_rub = max(0, int(amount_rub))
    minutes = max(0, int(minutes))
    created_at = _utc_now()
    payment_id = uuid4().hex
    provider_order_id = f"golos-{payment_id[:24]}"
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO account_payments (
                    payment_id, account_id, license_id, created_at, updated_at, amount_rub,
                    minutes, currency, status, provider, provider_order_id, provider_payment_id,
                    payment_url, description, error_code, error_message, paid_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, '', '', ?, '', '', '')
                """,
                (
                    payment_id,
                    account.account_id,
                    account.premium_license_id,
                    created_at,
                    created_at,
                    amount_rub,
                    minutes,
                    settings.payment_currency,
                    provider,
                    provider_order_id,
                    description.strip(),
                ),
            )
    payment = get_account_payment(settings, payment_id)
    if payment is None:
        raise RuntimeError("Payment was not created.")
    return payment


def get_account_payment(settings: ServerSettings, payment_id: str) -> AccountPayment | None:
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT payment_id, account_id, license_id, created_at, updated_at, amount_rub,
                   minutes, currency, status, provider, provider_order_id, provider_payment_id,
                   payment_url, description, error_code, error_message, paid_at
            FROM account_payments
            WHERE payment_id = ?
            """,
            (payment_id.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _account_payment_from_row(row)


def list_account_payments(settings: ServerSettings, account_id: str, limit: int = 20) -> list[AccountPayment]:
    limit = max(1, min(limit, 100))
    with closing(_connect(settings)) as db:
        rows = db.execute(
            """
            SELECT payment_id, account_id, license_id, created_at, updated_at, amount_rub,
                   minutes, currency, status, provider, provider_order_id, provider_payment_id,
                   payment_url, description, error_code, error_message, paid_at
            FROM account_payments
            WHERE account_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
    return [_account_payment_from_row(row) for row in rows]


def set_account_payment_url(settings: ServerSettings, payment_id: str, payment_url: str) -> AccountPayment:
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE account_payments
                SET updated_at = ?, payment_url = ?
                WHERE payment_id = ?
                """,
                (_utc_now(), payment_url.strip(), payment_id),
            )
    payment = get_account_payment(settings, payment_id)
    if payment is None:
        raise RuntimeError("Payment disappeared after update.")
    return payment


def mark_account_payment_failed(
    settings: ServerSettings,
    payment_id: str,
    error_code: str,
    error_message: str,
    status: str = "failed",
) -> AccountPayment:
    if status not in {"failed", "canceled"}:
        raise ValueError("Unsupported payment failure status.")
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE account_payments
                SET updated_at = ?, status = ?, error_code = ?, error_message = ?
                WHERE payment_id = ? AND status != 'paid'
                """,
                (_utc_now(), status, error_code.strip()[:100], error_message.strip()[:1000], payment_id),
            )
    payment = get_account_payment(settings, payment_id)
    if payment is None:
        raise RuntimeError("Payment disappeared after failure update.")
    return payment


def find_account_payment_by_order(settings: ServerSettings, provider: str, provider_order_id: str) -> AccountPayment | None:
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT payment_id, account_id, license_id, created_at, updated_at, amount_rub,
                   minutes, currency, status, provider, provider_order_id, provider_payment_id,
                   payment_url, description, error_code, error_message, paid_at
            FROM account_payments
            WHERE provider = ? AND provider_order_id = ?
            """,
            (provider, provider_order_id),
        ).fetchone()
    if row is None:
        return None
    return _account_payment_from_row(row)


def account_payment_operation_exists(settings: ServerSettings, provider: str, provider_payment_id: str) -> bool:
    if not provider_payment_id:
        return False
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT payment_id
            FROM account_payments
            WHERE provider = ? AND provider_payment_id = ?
            """,
            (provider, provider_payment_id),
        ).fetchone()
    return row is not None


def apply_paid_account_payment(
    settings: ServerSettings,
    payment_id: str,
    provider_payment_id: str = "",
) -> tuple[bool, AccountPayment]:
    payment = get_account_payment(settings, payment_id)
    if payment is None:
        raise ValueError("Payment not found.")
    if payment.status == "paid":
        return False, payment

    paid_at = _utc_now()
    seconds = max(0, payment.minutes) * 60
    with closing(_connect(settings)) as db:
        with db:
            cursor = db.execute(
                """
                UPDATE account_payments
                SET updated_at = ?, status = 'paid', provider_payment_id = ?, paid_at = ?
                WHERE payment_id = ? AND status != 'paid'
                """,
                (paid_at, provider_payment_id.strip(), paid_at, payment.payment_id),
            )
            applied = cursor.rowcount == 1
            if applied:
                db.execute(
                    """
                    UPDATE premium_licenses
                    SET updated_at = ?,
                        balance_seconds = balance_seconds + ?,
                        total_granted_seconds = total_granted_seconds + ?,
                        total_amount_rub = total_amount_rub + ?
                    WHERE license_id = ?
                    """,
                    (paid_at, seconds, seconds, payment.amount_rub, payment.license_id),
                )
                _insert_premium_ledger(
                    db,
                    payment.license_id,
                    "payment",
                    seconds,
                    payment.amount_rub,
                    f"Оплата {payment.payment_id}",
                )
    updated = get_account_payment(settings, payment.payment_id)
    if updated is None:
        raise RuntimeError("Payment disappeared after paid update.")
    return applied, updated


def create_client_action(settings: ServerSettings, license_id: str, action_type: str, message: str = "") -> ClientAction:
    license = get_premium_license(settings, license_id)
    if license is None:
        raise ValueError("Premium license not found.")
    if action_type not in {"diagnostics_request", "update_suggestion"}:
        raise ValueError("Unsupported client action type.")

    action_id = uuid4().hex
    created_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                INSERT INTO client_actions (
                    action_id, license_id, created_at, updated_at, action_type,
                    status, message, result_message
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, '')
                """,
                (action_id, license.license_id, created_at, created_at, action_type, message.strip()),
            )
    action = get_client_action(settings, action_id)
    if action is None:
        raise RuntimeError("Client action was not created.")
    return action


def get_client_action(settings: ServerSettings, action_id: str) -> ClientAction | None:
    with closing(_connect(settings)) as db:
        row = db.execute(
            """
            SELECT action_id, license_id, created_at, updated_at, action_type, status, message, result_message
            FROM client_actions
            WHERE action_id = ?
            """,
            (action_id.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _client_action_from_row(row)


def list_pending_client_actions(settings: ServerSettings, license_key: str, limit: int = 20) -> list[ClientAction]:
    license = get_premium_license(settings, license_key)
    if license is None:
        return []
    limit = max(1, min(limit, 50))
    with closing(_connect(settings)) as db:
        rows = db.execute(
            """
            SELECT action_id, license_id, created_at, updated_at, action_type, status, message, result_message
            FROM client_actions
            WHERE license_id = ? AND status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (license.license_id, limit),
        ).fetchall()
    return [_client_action_from_row(row) for row in rows]


def mark_client_action(
    settings: ServerSettings,
    action_id: str,
    license_key: str,
    status: str,
    result_message: str = "",
) -> ClientAction:
    license = get_premium_license(settings, license_key)
    action = get_client_action(settings, action_id)
    if license is None or action is None or action.license_id != license.license_id:
        raise ValueError("Client action not found.")
    if status not in {"done", "declined", "error", "seen"}:
        raise ValueError("Unsupported client action status.")

    updated_at = _utc_now()
    with closing(_connect(settings)) as db:
        with db:
            db.execute(
                """
                UPDATE client_actions
                SET updated_at = ?, status = ?, result_message = ?
                WHERE action_id = ? AND license_id = ?
                """,
                (updated_at, status, result_message.strip()[:1000], action.action_id, license.license_id),
            )
    updated = get_client_action(settings, action.action_id)
    if updated is None:
        raise RuntimeError("Client action disappeared after update.")
    return updated


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


def _client_action_from_row(row: tuple[object, ...]) -> ClientAction:
    return ClientAction(
        action_id=str(row[0]),
        license_id=str(row[1]),
        created_at=str(row[2]),
        updated_at=str(row[3]),
        action_type=str(row[4]),
        status=str(row[5]),
        message=str(row[6]),
        result_message=str(row[7]),
    )


def _account_from_row(row: tuple[object, ...]) -> Account:
    return Account(
        account_id=str(row[0]),
        created_at=str(row[1]),
        updated_at=str(row[2]),
        email=str(row[3]),
        name=str(row[4]),
        premium_license_id=str(row[5]),
        active=bool(row[6]),
        email_confirmed=bool(row[7]),
        last_seen_at=str(row[8]),
    )


def _account_payment_from_row(row: tuple[object, ...]) -> AccountPayment:
    return AccountPayment(
        payment_id=str(row[0]),
        account_id=str(row[1]),
        license_id=str(row[2]),
        created_at=str(row[3]),
        updated_at=str(row[4]),
        amount_rub=int(row[5]),
        minutes=int(row[6]),
        currency=str(row[7]),
        status=str(row[8]),
        provider=str(row[9]),
        provider_order_id=str(row[10]),
        provider_payment_id=str(row[11]),
        payment_url=str(row[12]),
        description=str(row[13]),
        error_code=str(row[14]),
        error_message=str(row[15]),
        paid_at=str(row[16]),
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


def _new_account_token() -> str:
    return f"golos_session_{secrets.token_urlsafe(32)}"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def account_token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    iterations = 260_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _utc_after(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=max(1, int(days)))).isoformat(timespec="seconds") + "Z"
