from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from voice_input.branding import asset_path
from voice_input.paths import runtime_base_dir


APP_SHORTCUT_NAME = "Голос.lnk"


@dataclass(slots=True)
class ShortcutStatus:
    start_menu_path: Path | None
    startup_path: Path | None
    start_menu_exists: bool
    startup_exists: bool


def is_windows() -> bool:
    return os.name == "nt"


def shortcut_status() -> ShortcutStatus:
    start_menu_path = _start_menu_shortcut_path()
    startup_path = _startup_shortcut_path()
    return ShortcutStatus(
        start_menu_path=start_menu_path,
        startup_path=startup_path,
        start_menu_exists=bool(start_menu_path and start_menu_path.exists()),
        startup_exists=bool(startup_path and startup_path.exists()),
    )


def sync_shortcuts(config_path: str | Path, run_on_windows_startup: bool) -> ShortcutStatus:
    if not is_windows():
        return shortcut_status()

    create_start_menu_shortcut(config_path)
    if run_on_windows_startup:
        create_startup_shortcut(config_path)
    else:
        remove_startup_shortcut()
    return shortcut_status()


def install_shortcuts(config_path: str | Path, run_on_windows_startup: bool = True) -> ShortcutStatus:
    if not is_windows():
        return shortcut_status()

    create_start_menu_shortcut(config_path)
    if run_on_windows_startup:
        create_startup_shortcut(config_path)
    return shortcut_status()


def remove_shortcuts() -> ShortcutStatus:
    remove_start_menu_shortcut()
    remove_startup_shortcut()
    return shortcut_status()


def create_start_menu_shortcut(config_path: str | Path) -> None:
    path = _start_menu_shortcut_path()
    if path is None:
        return
    _create_shortcut(path, config_path, open_settings=True)


def create_startup_shortcut(config_path: str | Path) -> None:
    path = _startup_shortcut_path()
    if path is None:
        return
    _create_shortcut(path, config_path, open_settings=False)


def remove_start_menu_shortcut() -> None:
    _remove_shortcut(_start_menu_shortcut_path())


def remove_startup_shortcut() -> None:
    _remove_shortcut(_startup_shortcut_path())


def _start_menu_shortcut_path() -> Path | None:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_SHORTCUT_NAME


def _startup_shortcut_path() -> Path | None:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / APP_SHORTCUT_NAME


def _remove_shortcut(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


def _create_shortcut(shortcut_path: Path, config_path: str | Path, *, open_settings: bool) -> None:
    target_path, arguments, working_directory = _launch_command(config_path, open_settings=open_settings)
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    icon_location = _shortcut_icon_location(target_path)
    window_style = "1" if open_settings else "7"

    env = os.environ.copy()
    env.update(
        {
            "GOLOS_SHORTCUT_PATH": str(shortcut_path),
            "GOLOS_SHORTCUT_TARGET": str(target_path),
            "GOLOS_SHORTCUT_ARGS": arguments,
            "GOLOS_SHORTCUT_WORKDIR": str(working_directory),
            "GOLOS_SHORTCUT_DESCRIPTION": "Голосовой ввод Голос",
            "GOLOS_SHORTCUT_ICON": icon_location,
            "GOLOS_SHORTCUT_WINDOW_STYLE": window_style,
        }
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _CREATE_SHORTCUT_SCRIPT,
        ],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _launch_command(config_path: str | Path, *, open_settings: bool) -> tuple[Path, str, Path]:
    resolved_config_path = Path(config_path).resolve()
    if getattr(sys, "frozen", False):
        target_path = Path(sys.executable).resolve()
        args = []
    else:
        target_path = _pythonw_executable()
        args = ["-m", "voice_input.app"]
    if open_settings:
        args.append("--settings")
    args.extend(["--config", str(resolved_config_path)])
    arguments = subprocess.list2cmdline(args)
    return target_path, arguments, runtime_base_dir()


def _pythonw_executable() -> Path:
    executable = Path(sys.executable).resolve()
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw
    return executable


def _shortcut_icon_location(target_path: Path) -> str:
    if getattr(sys, "frozen", False):
        return f"{target_path},0"
    icon_path = asset_path("golos.ico")
    if icon_path.exists():
        return str(icon_path)
    return f"{target_path},0"


_CREATE_SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$shortcutPath = $env:GOLOS_SHORTCUT_PATH
$targetPath = $env:GOLOS_SHORTCUT_TARGET
$arguments = $env:GOLOS_SHORTCUT_ARGS
$workingDirectory = $env:GOLOS_SHORTCUT_WORKDIR
$description = $env:GOLOS_SHORTCUT_DESCRIPTION
$iconLocation = $env:GOLOS_SHORTCUT_ICON
$windowStyle = [int]$env:GOLOS_SHORTCUT_WINDOW_STYLE

New-Item -ItemType Directory -Path (Split-Path -Parent $shortcutPath) -Force | Out-Null
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $workingDirectory
$shortcut.Description = $description
$shortcut.IconLocation = $iconLocation
$shortcut.WindowStyle = $windowStyle
$shortcut.Save()
"""
