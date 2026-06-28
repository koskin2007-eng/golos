from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from voice_input.config import PremiumSettings
from voice_input.env_file import default_env_path, env_value_exists, read_env_value


PREMIUM_KEY_NAME = "GOLOS_PREMIUM_KEY"


@dataclass(slots=True)
class PremiumBalance:
    active: bool
    license_id: str
    key_prefix: str
    balance_minutes: float
    total_granted_minutes: float
    total_used_minutes: float


def premium_key_exists(settings: PremiumSettings) -> bool:
    return bool(premium_key_from_env(settings))


def premium_key_from_env(settings: PremiumSettings) -> str:
    env_name = settings.license_key_env.strip() or PREMIUM_KEY_NAME
    return read_env_value(default_env_path(), env_name) or os.getenv(env_name, "")


def premium_env_value_exists(settings: PremiumSettings) -> bool:
    env_name = settings.license_key_env.strip() or PREMIUM_KEY_NAME
    return env_value_exists(default_env_path(), env_name) or bool(os.getenv(env_name))


def normalize_premium_key(value: str, env_name: str = PREMIUM_KEY_NAME) -> str:
    key = value.strip()
    if key.startswith(f"{env_name}="):
        key = key.split("=", 1)[1].strip()
    if key.startswith(f"{PREMIUM_KEY_NAME}="):
        key = key.split("=", 1)[1].strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    return key


def check_premium_balance(settings: PremiumSettings, license_key: str | None = None) -> PremiumBalance:
    server_url = settings.server_url.strip()
    if not server_url:
        raise RuntimeError("Адрес сервера Голос Премиум не указан.")

    key = license_key or premium_key_from_env(settings)
    if not key:
        raise RuntimeError("Премиум-ключ Голос не сохранён.")

    request = urllib.request.Request(
        server_url.rstrip("/") + "/api/premium/balance",
        headers={"X-Golos-Premium-Key": key},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return PremiumBalance(
        active=bool(payload.get("active", False)),
        license_id=str(payload.get("license_id", "")),
        key_prefix=str(payload.get("key_prefix", "")),
        balance_minutes=float(payload.get("balance_minutes", 0.0) or 0.0),
        total_granted_minutes=float(payload.get("total_granted_minutes", 0.0) or 0.0),
        total_used_minutes=float(payload.get("total_used_minutes", 0.0) or 0.0),
    )
