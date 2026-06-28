from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServerSettings:
    data_dir: Path
    support_token: str
    max_upload_bytes: int
    public_latest_json_url: str
    update_json_path: Path


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
        max_upload_bytes=int(os.getenv("GOLOS_MAX_UPLOAD_MB", "25")) * 1024 * 1024,
        public_latest_json_url=public_latest_json_url,
        update_json_path=update_json_path,
    )
