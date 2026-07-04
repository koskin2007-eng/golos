from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voice_input.paths import resolve_runtime_path

try:
    import yaml
except ImportError:  # pragma: no cover - handled at runtime with a clear error.
    yaml = None


DEFAULT_CONFIG_YAML = """hotkey: "F8"
language: "ru"
backend: "local_fast"
recognition_profile: "base"

profiles:
  tiny:
    backend: "local_fast"
    local_fast:
      model_size: "tiny"
      device: "cpu"
      compute_type: "int8"
      beam_size: 1
      vad_filter: true
  base:
    backend: "local_fast"
    local_fast:
      model_size: "base"
      device: "cpu"
      compute_type: "int8"
      beam_size: 1
      vad_filter: true
  small:
    backend: "local_fast"
    local_fast:
      model_size: "small"
      device: "cpu"
      compute_type: "int8"
      beam_size: 1
      vad_filter: true
  server:
    backend: "server_proxy"
  openai:
    backend: "openai"
  premium:
    backend: "premium_proxy"

audio:
  sample_rate: 16000
  channels: 1
  device: null

local_fast:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
  beam_size: 1
  vad_filter: true

local_quality:
  model_size: "medium"
  device: "auto"
  compute_type: "auto"
  beam_size: 3
  vad_filter: true

openai:
  model: "gpt-4o-mini-transcribe"
  response_format: "text"

server_stt:
  server_url: "https://golos.msgcrm.ru"
  model: "base"

premium:
  server_url: "https://golos.msgcrm.ru"
  license_key_env: "GOLOS_PREMIUM_KEY"
  model: "gpt-4o-mini-transcribe"

text_correction:
  enabled: false
  model: "gpt-5.4-mini"

paste:
  method: "clipboard_ctrl_v"
  restore_clipboard: false
  restore_delay_ms: 800
  add_space_after_text: true

feedback:
  beep_on_recording: true

startup:
  run_on_windows_startup: false

logs:
  level: "INFO"

performance:
  preload_model: false

support:
  server_url: ""
  token_env: "GOLOS_SUPPORT_TOKEN"
"""


DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "hotkey": "F8",
    "language": "ru",
    "backend": "local_fast",
    "recognition_profile": "base",
    "profiles": {
        "tiny": {
            "backend": "local_fast",
            "local_fast": {
                "model_size": "tiny",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "vad_filter": True,
            },
        },
        "base": {
            "backend": "local_fast",
            "local_fast": {
                "model_size": "base",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "vad_filter": True,
            },
        },
        "small": {
            "backend": "local_fast",
            "local_fast": {
                "model_size": "small",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "vad_filter": True,
            },
        },
        "server": {
            "backend": "server_proxy",
        },
        "openai": {
            "backend": "openai",
        },
        "premium": {
            "backend": "premium_proxy",
        },
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device": None,
    },
    "local_fast": {
        "model_size": "base",
        "device": "cpu",
        "compute_type": "int8",
        "beam_size": 1,
        "vad_filter": True,
    },
    "local_quality": {
        "model_size": "medium",
        "device": "auto",
        "compute_type": "auto",
        "beam_size": 3,
        "vad_filter": True,
    },
    "openai": {
        "model": "gpt-4o-mini-transcribe",
        "response_format": "text",
    },
    "server_stt": {
        "server_url": "https://golos.msgcrm.ru",
        "model": "base",
    },
    "premium": {
        "server_url": "https://golos.msgcrm.ru",
        "license_key_env": "GOLOS_PREMIUM_KEY",
        "model": "gpt-4o-mini-transcribe",
    },
    "text_correction": {
        "enabled": False,
        "model": "gpt-5.4-mini",
    },
    "paste": {
        "method": "clipboard_ctrl_v",
        "restore_clipboard": False,
        "restore_delay_ms": 800,
        "add_space_after_text": True,
    },
    "feedback": {
        "beep_on_recording": True,
    },
    "startup": {
        "run_on_windows_startup": False,
    },
    "logs": {
        "level": "INFO",
    },
    "performance": {
        "preload_model": False,
    },
    "support": {
        "server_url": "",
        "token_env": "GOLOS_SUPPORT_TOKEN",
    },
}


@dataclass(slots=True)
class AudioSettings:
    sample_rate: int = 16000
    channels: int = 1
    device: str | int | None = None


@dataclass(slots=True)
class LocalWhisperSettings:
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    vad_filter: bool = True


@dataclass(slots=True)
class OpenAISettings:
    model: str = "gpt-4o-mini-transcribe"
    response_format: str = "text"


@dataclass(slots=True)
class ServerSTTSettings:
    server_url: str = "https://golos.msgcrm.ru"
    model: str = "base"


@dataclass(slots=True)
class PremiumSettings:
    server_url: str = "https://golos.msgcrm.ru"
    license_key_env: str = "GOLOS_PREMIUM_KEY"
    model: str = "gpt-4o-mini-transcribe"


@dataclass(slots=True)
class TextCorrectionSettings:
    enabled: bool = False
    model: str = "gpt-5.4-mini"


@dataclass(slots=True)
class PasteSettings:
    method: str = "clipboard_ctrl_v"
    restore_clipboard: bool = False
    restore_delay_ms: int = 800
    add_space_after_text: bool = True


@dataclass(slots=True)
class FeedbackSettings:
    beep_on_recording: bool = True


@dataclass(slots=True)
class StartupSettings:
    run_on_windows_startup: bool = False


@dataclass(slots=True)
class LogSettings:
    level: str = "INFO"


@dataclass(slots=True)
class PerformanceSettings:
    preload_model: bool = False


@dataclass(slots=True)
class SupportSettings:
    server_url: str = ""
    token_env: str = "GOLOS_SUPPORT_TOKEN"


@dataclass(slots=True)
class AppConfig:
    hotkey: str
    language: str
    backend: str
    recognition_profile: str
    profiles: dict[str, Any]
    audio: AudioSettings
    local_fast: LocalWhisperSettings
    local_quality: LocalWhisperSettings
    openai: OpenAISettings
    server_stt: ServerSTTSettings
    premium: PremiumSettings
    text_correction: TextCorrectionSettings
    paste: PasteSettings
    feedback: FeedbackSettings
    startup: StartupSettings
    logs: LogSettings
    performance: PerformanceSettings
    support: SupportSettings


def deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def apply_recognition_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(data.get("recognition_profile") or "").strip()
    if not profile_name:
        return data

    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise ValueError("config.yaml profiles must be a mapping.")
    if profile_name not in profiles:
        available = ", ".join(sorted(str(name) for name in profiles)) or "none"
        raise ValueError(f"Unknown recognition_profile={profile_name!r}. Available profiles: {available}.")

    selected = profiles[profile_name]
    if not isinstance(selected, dict):
        raise ValueError(f"Profile {profile_name!r} must be a mapping.")

    allowed_keys = {"backend", "local_fast", "local_quality", "openai", "server_stt", "premium"}
    overrides = {key: value for key, value in selected.items() if key in allowed_keys}
    return deep_merge(data, overrides)


def build_config(data: dict[str, Any]) -> AppConfig:
    return AppConfig(
        hotkey=str(data["hotkey"]),
        language=str(data["language"]),
        backend=str(data["backend"]),
        recognition_profile=str(data.get("recognition_profile") or ""),
        profiles=data.get("profiles") or {},
        audio=AudioSettings(**data["audio"]),
        local_fast=LocalWhisperSettings(**data["local_fast"]),
        local_quality=LocalWhisperSettings(**data["local_quality"]),
        openai=OpenAISettings(**data["openai"]),
        server_stt=ServerSTTSettings(**data["server_stt"]),
        premium=PremiumSettings(**data["premium"]),
        text_correction=TextCorrectionSettings(**data["text_correction"]),
        paste=PasteSettings(**data["paste"]),
        feedback=FeedbackSettings(**data["feedback"]),
        startup=StartupSettings(**data["startup"]),
        logs=LogSettings(**data["logs"]),
        performance=PerformanceSettings(**data["performance"]),
        support=SupportSettings(**data["support"]),
    )


class ConfigManager:
    def __init__(self, path: str | Path = "config.yaml") -> None:
        self.path = resolve_runtime_path(path)

    def create_default(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")

    def _read_yaml_mapping(self) -> dict[str, Any]:
        if not self.path.exists():
            self.create_default()
        if yaml is None:
            raise RuntimeError("PyYAML is required to edit config.yaml. Run .\\run.ps1 first.")

        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("config.yaml must contain a YAML mapping at the top level.")
        return raw

    def _write_yaml_mapping(self, data: dict[str, Any]) -> None:
        if yaml is None:
            raise RuntimeError("PyYAML is required to edit config.yaml. Run .\\run.ps1 first.")
        self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def list_profiles(self) -> list[str]:
        raw = self._read_yaml_mapping()
        data = deep_merge(DEFAULT_CONFIG_DATA, raw)
        profiles = data.get("profiles") or {}
        if not isinstance(profiles, dict):
            raise ValueError("config.yaml profiles must be a mapping.")
        return sorted(str(name) for name in profiles)

    def get_selected_profile(self) -> str:
        raw = self._read_yaml_mapping()
        data = deep_merge(DEFAULT_CONFIG_DATA, raw)
        return str(data.get("recognition_profile") or "")

    def set_profile(self, profile_name: str) -> None:
        raw = self._read_yaml_mapping()
        data = deep_merge(DEFAULT_CONFIG_DATA, raw)
        profiles = data.get("profiles") or {}
        if not isinstance(profiles, dict):
            raise ValueError("config.yaml profiles must be a mapping.")
        if profile_name not in profiles:
            available = ", ".join(sorted(str(name) for name in profiles)) or "none"
            raise ValueError(f"Unknown profile {profile_name!r}. Available profiles: {available}.")
        raw["recognition_profile"] = profile_name
        self._write_yaml_mapping(raw)

    def set_startup_enabled(self, enabled: bool) -> None:
        raw = self._read_yaml_mapping()
        raw.setdefault("startup", {})["run_on_windows_startup"] = bool(enabled)
        self._write_yaml_mapping(raw)

    def load(self) -> AppConfig:
        created = False
        if not self.path.exists():
            self.create_default()
            created = True

        if yaml is None:
            text = self.path.read_text(encoding="utf-8")
            if created or text.strip() == DEFAULT_CONFIG_YAML.strip():
                data = copy.deepcopy(DEFAULT_CONFIG_DATA)
            else:
                raise RuntimeError("PyYAML is required to read a custom config.yaml. Run .\\run.ps1 first.")
        else:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("config.yaml must contain a YAML mapping at the top level.")
            data = deep_merge(DEFAULT_CONFIG_DATA, raw)

        data = apply_recognition_profile(data)
        return build_config(data)
