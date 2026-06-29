from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from voice_input.config import PremiumSettings
from voice_input.premium import premium_auth_headers


@dataclass(slots=True)
class RemoteAction:
    action_id: str
    action_type: str
    message: str
    created_at: str


def fetch_remote_actions(settings: PremiumSettings) -> list[RemoteAction]:
    server_url = settings.server_url.strip()
    auth_headers = premium_auth_headers(settings)
    if not server_url or not auth_headers:
        return []

    request = urllib.request.Request(
        server_url.rstrip("/") + "/api/client/actions",
        headers=auth_headers,
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        return []
    return [
        RemoteAction(
            action_id=str(action.get("action_id", "")),
            action_type=str(action.get("action_type", "")),
            message=str(action.get("message", "")),
            created_at=str(action.get("created_at", "")),
        )
        for action in actions
        if isinstance(action, dict) and action.get("action_id")
    ]


def complete_remote_action(settings: PremiumSettings, action_id: str, status: str, message: str = "") -> None:
    server_url = settings.server_url.strip()
    auth_headers = premium_auth_headers(settings)
    if not server_url or not auth_headers:
        return

    body = json.dumps({"status": status, "message": message}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        server_url.rstrip("/") + f"/api/client/actions/{action_id}/complete",
        data=body,
        headers={
            "Content-Type": "application/json",
            **auth_headers,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()
