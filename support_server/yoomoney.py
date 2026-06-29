from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import quote

from support_server.settings import ServerSettings
from support_server.storage import AccountPayment


YOOMONEY_PROVIDER = "yoomoney"
YOOMONEY_QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm"
YOOMONEY_RUB_CURRENCY_CODE = "643"


@dataclass(frozen=True, slots=True)
class YooMoneyPaymentForm:
    action_url: str
    fields: dict[str, str]


def yoomoney_is_configured(settings: ServerSettings) -> bool:
    return bool(settings.yoomoney_receiver and settings.yoomoney_notification_secret)


def yoomoney_success_url(payment: AccountPayment, settings: ServerSettings) -> str:
    return f"{settings.public_app_url.rstrip('/')}/account/payments/{payment.payment_id}"


def build_yoomoney_payment_form(payment: AccountPayment, settings: ServerSettings) -> YooMoneyPaymentForm:
    if not settings.yoomoney_receiver:
        raise ValueError("GOLOS_YOOMONEY_RECEIVER is not configured.")
    if not payment.provider_order_id:
        raise ValueError("payment.provider_order_id is required.")

    return YooMoneyPaymentForm(
        action_url=YOOMONEY_QUICKPAY_URL,
        fields={
            "receiver": settings.yoomoney_receiver,
            "label": payment.provider_order_id,
            "quickpay-form": "button",
            "sum": f"{payment.amount_rub:.2f}",
            "paymentType": "AC",
            "successURL": yoomoney_success_url(payment, settings),
        },
    )


def canonical_yoomoney_notification(payload: dict[str, str]) -> str:
    parts: list[str] = []
    for key in sorted(payload):
        if key == "sign":
            continue
        parts.append(f"{key}={quote(str(payload.get(key, '')), safe='')}")
    return "&".join(parts)


def verify_yoomoney_notification(payload: dict[str, str], secret: str) -> bool:
    received_sign = str(payload.get("sign") or "")
    if not received_sign or not secret:
        return False
    canonical = canonical_yoomoney_notification(payload)
    expected_sign = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sign, received_sign)


def validate_yoomoney_payment_payload(
    payload: dict[str, str],
    *,
    expected_label: str,
    expected_amount_rub: int,
) -> str | None:
    if payload.get("label") != expected_label:
        return "label_mismatch"
    if not payload.get("operation_id"):
        return "operation_id_missing"
    if payload.get("currency") != YOOMONEY_RUB_CURRENCY_CODE:
        return "currency_mismatch"
    if _payload_bool(payload.get("codepro")):
        return "codepro_payment_not_supported"
    if _payload_bool(payload.get("unaccepted")):
        return "payment_unaccepted"

    withdraw_amount = _payload_amount_rub(payload.get("withdraw_amount"))
    if withdraw_amount is None:
        return "withdraw_amount_invalid"
    if withdraw_amount < int(expected_amount_rub):
        return "amount_mismatch"
    return None


def _payload_bool(value: str | None) -> bool:
    return str(value or "").lower() == "true"


def _payload_amount_rub(value: str | None) -> int | None:
    try:
        return int(round(float(str(value or "0").replace(",", "."))))
    except ValueError:
        return None
