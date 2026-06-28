from __future__ import annotations

import platform
import sys
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voice_input.diagnostics import collect_diagnostics
from voice_input.paths import resolve_runtime_path, runtime_base_dir
from voice_input.version import APP_VERSION, GITHUB_REPOSITORY


@dataclass(slots=True)
class SupportPackage:
    archive_path: Path
    issue_body_path: Path
    issue_url: str


def create_support_package(config_path: str | Path, log_path: str | Path) -> SupportPackage:
    archive_path = collect_diagnostics(config_path, log_path)
    issue_body = _support_issue_body(archive_path, Path(config_path).resolve(), Path(log_path).resolve())
    issue_body_path = archive_path.with_name(f"{archive_path.stem}_github_issue.txt")
    issue_body_path.write_text(issue_body, encoding="utf-8")
    issue_url = _github_issue_url(issue_body)
    return SupportPackage(archive_path=archive_path, issue_body_path=issue_body_path, issue_url=issue_url)


def open_support_package(package: SupportPackage) -> None:
    _copy_to_clipboard(package.issue_body_path.read_text(encoding="utf-8"))
    webbrowser.open(package.issue_url)
    if package.archive_path.parent.exists():
        import os

        os.startfile(str(package.archive_path.parent))  # noqa: S606 - Windows desktop helper.


def _support_issue_body(archive_path: Path, config_path: Path, log_path: Path) -> str:
    created_at = datetime.now().isoformat(timespec="seconds")
    return "\n".join(
        [
            "## Что произошло",
            "",
            "Опишите проблему: что нажали, что ожидали, что произошло.",
            "",
            "## Диагностика",
            "",
            f"Диагностический архив создан: `{archive_path}`",
            "Прикрепите этот ZIP-файл к обращению на GitHub.",
            "",
            "## Данные программы",
            "",
            f"- Версия Голос: {APP_VERSION}",
            f"- Создано: {created_at}",
            f"- Windows/Python: {platform.platform()} / {sys.version.split()[0]}",
            f"- Папка программы: `{runtime_base_dir()}`",
            f"- Конфиг: `{config_path}`",
            f"- Лог: `{log_path}`",
            "",
            "## Безопасность",
            "",
            "Архив не должен содержать `.env`, OpenAI API key, временное аудио, модели или приватные ключи.",
            "",
        ]
    )


def _github_issue_url(issue_body: str) -> str:
    query = urllib.parse.urlencode(
        {
            "title": f"Диагностика Голос {APP_VERSION}",
            "body": issue_body,
        }
    )
    return f"https://github.com/{GITHUB_REPOSITORY}/issues/new?{query}"


def _copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
    except Exception:  # noqa: BLE001
        return
