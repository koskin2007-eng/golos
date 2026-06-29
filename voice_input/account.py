from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin

from voice_input.env_file import default_env_path, env_value_exists, read_env_value, set_env_value


ACCOUNT_TOKEN_NAME = "GOLOS_ACCOUNT_TOKEN"
ACCOUNT_EMAIL_NAME = "GOLOS_ACCOUNT_EMAIL"
DEFAULT_ACCOUNT_SERVER_URL = "https://golos.msgcrm.ru"


@dataclass(slots=True)
class AccountInfo:
    email: str
    name: str
    balance_minutes: float
    total_granted_minutes: float
    total_used_minutes: float


@dataclass(slots=True)
class AccountPaymentInfo:
    payment_id: str
    amount_rub: int
    minutes: int
    status: str
    provider: str
    payment_url: str
    error_message: str


@dataclass(slots=True)
class AccountSession:
    token: str
    account: AccountInfo


def account_token_from_env() -> str:
    return read_env_value(default_env_path(), ACCOUNT_TOKEN_NAME) or os.getenv(ACCOUNT_TOKEN_NAME, "")


def account_email_from_env() -> str:
    return read_env_value(default_env_path(), ACCOUNT_EMAIL_NAME) or os.getenv(ACCOUNT_EMAIL_NAME, "")


def account_token_exists() -> bool:
    return env_value_exists(default_env_path(), ACCOUNT_TOKEN_NAME) or bool(os.getenv(ACCOUNT_TOKEN_NAME))


def save_account_session(email: str, token: str) -> None:
    set_env_value(default_env_path(), ACCOUNT_EMAIL_NAME, email.strip())
    set_env_value(default_env_path(), ACCOUNT_TOKEN_NAME, token.strip())
    os.environ[ACCOUNT_EMAIL_NAME] = email.strip()
    os.environ[ACCOUNT_TOKEN_NAME] = token.strip()


def clear_account_session() -> None:
    set_env_value(default_env_path(), ACCOUNT_TOKEN_NAME, "")
    os.environ.pop(ACCOUNT_TOKEN_NAME, None)


def register_account(server_url: str, email: str, password: str, name: str = "") -> AccountSession:
    payload = _post_json(
        server_url,
        "/api/account/register",
        {"email": email, "password": password, "name": name},
    )
    return _session_from_payload(payload)


def login_account(server_url: str, email: str, password: str) -> AccountSession:
    payload = _post_json(
        server_url,
        "/api/account/login",
        {"email": email, "password": password},
    )
    return _session_from_payload(payload)


def logout_account(server_url: str, token: str | None = None) -> None:
    token = token or account_token_from_env()
    if token:
        try:
            _post_json(server_url, "/api/account/logout", {}, token=token)
        except Exception:
            pass
    clear_account_session()


def fetch_account(server_url: str, token: str | None = None) -> AccountInfo:
    payload = _get_json(server_url, "/api/account/me", token=token or account_token_from_env())
    return _account_from_payload(payload.get("account") or {})


def create_account_payment(server_url: str, amount_rub: int, token: str | None = None) -> AccountPaymentInfo:
    payload = _post_json(
        server_url,
        "/api/account/payments",
        {"amount_rub": int(amount_rub)},
        token=token or account_token_from_env(),
    )
    payment = _payment_from_payload(payload.get("payment") or {})
    if payment.payment_url and payment.payment_url.startswith("/"):
        payment.payment_url = urljoin(_normalize_server_url(server_url) + "/", payment.payment_url.lstrip("/"))
    return payment


def account_auth_headers() -> dict[str, str]:
    token = account_token_from_env()
    if not token:
        return {}
    return {"X-Golos-Account-Token": token}


def _session_from_payload(payload: dict[str, object]) -> AccountSession:
    token = str(payload.get("account_token") or "")
    if not token:
        raise RuntimeError("Сервер не вернул токен аккаунта.")
    account = _account_from_payload(payload.get("account") or {})
    return AccountSession(token=token, account=account)


def _account_from_payload(payload: object) -> AccountInfo:
    if not isinstance(payload, dict):
        payload = {}
    return AccountInfo(
        email=str(payload.get("email") or ""),
        name=str(payload.get("name") or ""),
        balance_minutes=float(payload.get("balance_minutes", 0.0) or 0.0),
        total_granted_minutes=float(payload.get("total_granted_minutes", 0.0) or 0.0),
        total_used_minutes=float(payload.get("total_used_minutes", 0.0) or 0.0),
    )


def _payment_from_payload(payload: object) -> AccountPaymentInfo:
    if not isinstance(payload, dict):
        payload = {}
    return AccountPaymentInfo(
        payment_id=str(payload.get("payment_id") or ""),
        amount_rub=int(payload.get("amount_rub", 0) or 0),
        minutes=int(payload.get("minutes", 0) or 0),
        status=str(payload.get("status") or ""),
        provider=str(payload.get("provider") or ""),
        payment_url=str(payload.get("payment_url") or ""),
        error_message=str(payload.get("error_message") or ""),
    )


def _get_json(server_url: str, path: str, token: str = "") -> dict[str, object]:
    request = urllib.request.Request(
        _build_url(server_url, path),
        headers=_headers(token),
        method="GET",
    )
    return _open_json(request)


def _post_json(server_url: str, path: str, payload: dict[str, object], token: str = "") -> dict[str, object]:
    request = urllib.request.Request(
        _build_url(server_url, path),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(token),
        method="POST",
    )
    return _open_json(request)


def _headers(token: str = "") -> dict[str, str]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if token:
        headers["X-Golos-Account-Token"] = token
    return headers


def _open_json(request: urllib.request.Request) -> dict[str, object]:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8")
            parsed = json.loads(body)
            detail = str(parsed.get("detail") or "")
        except Exception:
            detail = str(exc)
        raise RuntimeError(detail or str(exc)) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Сервер вернул неожиданный ответ.")
    return payload


def _build_url(server_url: str, path: str) -> str:
    return _normalize_server_url(server_url) + "/" + path.lstrip("/")


def _normalize_server_url(server_url: str) -> str:
    return (server_url or DEFAULT_ACCOUNT_SERVER_URL).strip().rstrip("/")
