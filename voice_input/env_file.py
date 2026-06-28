from __future__ import annotations

from pathlib import Path

from voice_input.paths import resolve_runtime_path


OPENAI_API_KEY_NAME = "OPENAI_API_KEY"


def default_env_path() -> Path:
    return resolve_runtime_path(".env")


def env_value_exists(path: str | Path, name: str) -> bool:
    return bool(read_env_value(path, name))


def read_env_value(path: str | Path, name: str) -> str:
    env_path = Path(path)
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        key, value = _split_env_line(line)
        if key == name:
            return value
    return ""


def set_env_value(path: str | Path, name: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError("Env value must be a single line.")

    env_path = Path(path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []

    replacement = f"{name}={_format_env_value(value)}"
    replaced = False
    updated: list[str] = []
    for line in lines:
        key, _value = _split_env_line(line)
        if key == name:
            updated.append(replacement)
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(replacement)

    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def normalize_openai_api_key(value: str) -> str:
    key = value.strip()
    if key.startswith(f"{OPENAI_API_KEY_NAME}="):
        key = key.split("=", 1)[1].strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    return key


def _split_env_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return "", ""
    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return "", ""
    key, value = stripped.split("=", 1)
    return key.strip(), _unquote_env_value(value.strip())


def _format_env_value(value: str) -> str:
    if value and not any(ch.isspace() for ch in value) and "#" not in value and '"' not in value and "'" not in value:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote_env_value(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\\\", "\\")
