from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServerSettings:
    data_dir: Path
    support_token: str
    admin_token: str
    admin_username: str
    admin_password: str
    max_upload_bytes: int
    public_latest_json_url: str
    update_json_path: Path
    public_app_url: str
    payments_mode: str
    payments_provider: str
    payment_currency: str
    payment_min_amount_rub: int
    payment_max_amount_rub: int
    payment_default_amount_rub: int
    premium_minutes_per_100_rub: int
    yoomoney_receiver: str
    yoomoney_notification_secret: str
    stt_enabled: bool
    stt_model_size: str
    stt_device: str
    stt_compute_type: str
    stt_beam_size: int
    stt_vad_filter: bool
    stt_max_duration_seconds: int
    stt_rate_limit_per_minute: int


def load_settings() -> ServerSettings:
    data_dir = Path(os.getenv("GOLOS_SUPPORT_DATA_DIR", "support_server/data")).resolve()
    public_latest_json_url = os.getenv(
        "GOLOS_PUBLIC_LATEST_JSON_URL",
        "https://github.com/koskin2007-eng/golos/releases/latest/download/latest.json",
    )
    update_json_path = Path(os.getenv("GOLOS_UPDATE_JSON_PATH", str(data_dir / "latest.json"))).resolve()
    return ServerSettings(
        data_dir=data_dir,
        support_token=os.getenv("GOLOS_SUPPORT_TOKEN", ""),
        admin_token=os.getenv("GOLOS_ADMIN_TOKEN", ""),
        admin_username=os.getenv("GOLOS_ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("GOLOS_ADMIN_PASSWORD", ""),
        max_upload_bytes=int(os.getenv("GOLOS_MAX_UPLOAD_MB", "25")) * 1024 * 1024,
        public_latest_json_url=public_latest_json_url,
        update_json_path=update_json_path,
        public_app_url=os.getenv("GOLOS_PUBLIC_APP_URL", "https://golos.msgcrm.ru"),
        payments_mode=os.getenv("GOLOS_PAYMENTS_MODE", "mock"),
        payments_provider=os.getenv("GOLOS_PAYMENTS_PROVIDER", "yoomoney"),
        payment_currency=os.getenv("GOLOS_PAYMENT_CURRENCY", "RUB"),
        payment_min_amount_rub=int(os.getenv("GOLOS_PAYMENT_MIN_AMOUNT_RUB", "100")),
        payment_max_amount_rub=int(os.getenv("GOLOS_PAYMENT_MAX_AMOUNT_RUB", "15000")),
        payment_default_amount_rub=int(os.getenv("GOLOS_PAYMENT_DEFAULT_AMOUNT_RUB", "100")),
        premium_minutes_per_100_rub=int(os.getenv("GOLOS_PREMIUM_MINUTES_PER_100_RUB", "180")),
        yoomoney_receiver=os.getenv("GOLOS_YOOMONEY_RECEIVER", ""),
        yoomoney_notification_secret=os.getenv("GOLOS_YOOMONEY_NOTIFICATION_SECRET", ""),
        stt_enabled=_env_bool("GOLOS_STT_ENABLED", False),
        stt_model_size=os.getenv("GOLOS_STT_MODEL_SIZE", "base"),
        stt_device=os.getenv("GOLOS_STT_DEVICE", "cpu"),
        stt_compute_type=os.getenv("GOLOS_STT_COMPUTE_TYPE", "int8"),
        stt_beam_size=int(os.getenv("GOLOS_STT_BEAM_SIZE", "1")),
        stt_vad_filter=_env_bool("GOLOS_STT_VAD_FILTER", True),
        stt_max_duration_seconds=int(os.getenv("GOLOS_STT_MAX_DURATION_SECONDS", "120")),
        stt_rate_limit_per_minute=int(os.getenv("GOLOS_STT_RATE_LIMIT_PER_MINUTE", "30")),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
