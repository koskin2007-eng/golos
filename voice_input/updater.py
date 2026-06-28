from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from voice_input.paths import resolve_runtime_path, runtime_base_dir
from voice_input.version import APP_VERSION, LATEST_RELEASE_JSON_URL


UPDATE_REQUEST_FILE = Path("temp") / "update.request.json"
UPDATE_SCRIPT_NAME = "apply_update.ps1"
PRESERVED_RUNTIME_NAMES = {
    ".env",
    ".env.local",
    "config.yaml",
    "diagnostics",
    "logs",
    "models",
    "temp",
    "updates",
}


@dataclass(slots=True)
class UpdateInfo:
    version: str
    tag: str
    asset: str
    sha256: str
    url: str


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    message: str
    info: UpdateInfo | None = None


@dataclass(slots=True)
class PreparedUpdate:
    version: str
    tag: str
    package_path: Path
    source_dir: Path


@dataclass(slots=True)
class UpdateInstallRequest:
    version: str
    tag: str
    package_path: Path
    source_dir: Path
    requesting_pid: int


def check_for_update(url: str = LATEST_RELEASE_JSON_URL, current_version: str = APP_VERSION) -> UpdateCheckResult:
    info = fetch_latest_release(url)
    latest = _version_tuple(info.version)
    current = _version_tuple(current_version)
    update_available = latest > current
    if latest > current:
        message = f"Доступна новая версия {info.version}."
    elif latest < current:
        message = f"Текущая версия {current_version} новее публичного релиза {info.version}."
    else:
        message = f"Установлена актуальная версия {current_version}."
    return UpdateCheckResult(
        current_version=current_version,
        latest_version=info.version,
        update_available=update_available,
        message=message,
        info=info,
    )


def fetch_latest_release(url: str = LATEST_RELEASE_JSON_URL) -> UpdateInfo:
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    return UpdateInfo(
        version=str(payload["version"]),
        tag=str(payload["tag"]),
        asset=str(payload["asset"]),
        sha256=str(payload["sha256"]).lower(),
        url=str(payload["url"]),
    )


def download_update(info: UpdateInfo, output_dir: str | Path = "updates") -> Path:
    target_dir = resolve_runtime_path(output_dir) / info.tag
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / info.asset
    temp_path = target_path.with_suffix(target_path.suffix + ".part")

    hasher = hashlib.sha256()
    with urllib.request.urlopen(info.url, timeout=120) as response, temp_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            output.write(chunk)

    actual = hasher.hexdigest().lower()
    if actual != info.sha256:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 не совпал: ожидали {info.sha256}, получили {actual}.")

    if target_path.exists():
        target_path.unlink()
    temp_path.rename(target_path)
    return target_path


def prepare_update_install(info: UpdateInfo, output_dir: str | Path = "updates") -> PreparedUpdate:
    package_path = download_update(info, output_dir)
    source_dir = extract_update_package(package_path, info.tag, output_dir)
    return PreparedUpdate(
        version=info.version,
        tag=info.tag,
        package_path=package_path,
        source_dir=source_dir,
    )


def extract_update_package(package_path: str | Path, tag: str, output_dir: str | Path = "updates") -> Path:
    package = Path(package_path).resolve()
    updates_root = resolve_runtime_path(output_dir).resolve()
    update_root = (updates_root / tag).resolve()
    extracting_dir = (update_root / "extracting").resolve()
    extracted_dir = (update_root / "extracted").resolve()

    _ensure_child_path(update_root, updates_root)
    _safe_rmtree(extracting_dir, updates_root)
    _safe_rmtree(extracted_dir, updates_root)
    extracting_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"Unsafe update archive path: {member.filename}")
            target_path = (extracting_dir / member_path).resolve()
            _ensure_child_path(target_path, extracting_dir)
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)

    source_dir = extracting_dir / "Golos"
    if not source_dir.exists():
        source_dir = extracting_dir
    if not (source_dir / "Golos.exe").exists():
        raise RuntimeError("Update archive does not contain Golos.exe.")

    extracting_dir.rename(extracted_dir)
    return (extracted_dir / source_dir.relative_to(extracting_dir)).resolve()


def update_install_request_path() -> Path:
    return resolve_runtime_path(UPDATE_REQUEST_FILE)


def write_update_install_request(prepared: PreparedUpdate) -> Path:
    path = update_install_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": prepared.version,
        "tag": prepared.tag,
        "package_path": str(prepared.package_path.resolve()),
        "source_dir": str(prepared.source_dir.resolve()),
        "requesting_pid": os.getpid(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_update_install_request() -> UpdateInstallRequest:
    payload = json.loads(update_install_request_path().read_text(encoding="utf-8"))
    return UpdateInstallRequest(
        version=str(payload["version"]),
        tag=str(payload["tag"]),
        package_path=Path(str(payload["package_path"])).resolve(),
        source_dir=Path(str(payload["source_dir"])).resolve(),
        requesting_pid=int(payload.get("requesting_pid") or 0),
    )


def clear_update_install_request() -> None:
    update_install_request_path().unlink(missing_ok=True)


def schedule_update_install(
    request: UpdateInstallRequest,
    config_path: str | Path,
    wait_pid: int | None = None,
) -> Path:
    if os.name != "nt":
        raise RuntimeError("Automatic update install is supported only on Windows.")
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Automatic update install is available only in the release EXE.")

    target_dir = runtime_base_dir().resolve()
    source_dir = request.source_dir.resolve()
    if not source_dir.exists():
        raise RuntimeError(f"Update source folder not found: {source_dir}")
    if not (source_dir / "Golos.exe").exists():
        raise RuntimeError(f"Update source does not contain Golos.exe: {source_dir}")

    updates_dir = resolve_runtime_path("updates") / request.tag
    updates_dir.mkdir(parents=True, exist_ok=True)
    script_path = updates_dir / UPDATE_SCRIPT_NAME
    script_path.write_text(
        _build_windows_update_script(
            target_dir=target_dir,
            source_dir=source_dir,
            config_path=Path(config_path).resolve(),
            tag=request.tag,
            wait_pids=[pid for pid in (wait_pid, request.requesting_pid) if pid and pid > 0],
        ),
        encoding="utf-8",
    )

    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        cwd=str(target_dir),
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return script_path


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in version.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _ensure_child_path(path: Path, parent: Path) -> None:
    path = path.resolve()
    parent = parent.resolve()
    if path == parent:
        return
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to use path outside update folder: {path}") from exc


def _safe_rmtree(path: Path, parent: Path) -> None:
    if not path.exists():
        return
    _ensure_child_path(path, parent)
    shutil.rmtree(path)


def _ps_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _build_windows_update_script(
    target_dir: Path,
    source_dir: Path,
    config_path: Path,
    tag: str,
    wait_pids: list[int],
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"backup-{tag}-{timestamp}"
    wait_pid_lines = "\n".join(
        f"try {{ Wait-Process -Id {pid} -Timeout 45 -ErrorAction SilentlyContinue }} catch {{ }}"
        for pid in wait_pids
        if pid != os.getpid()
    )
    preserve = ", ".join(_ps_string(name) for name in sorted(PRESERVED_RUNTIME_NAMES))
    return f"""$ErrorActionPreference = 'Stop'
$TargetDir = {_ps_string(target_dir)}
$SourceDir = {_ps_string(source_dir)}
$ConfigPath = {_ps_string(config_path)}
$BackupName = {_ps_string(backup_name)}
$PreserveNames = @({preserve})
$LogPath = Join-Path $TargetDir 'updates\\last_update.log'

function Write-UpdateLog([string]$Message) {{
    $line = "$(Get-Date -Format s) $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}}

try {{
    New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
    Write-UpdateLog 'Waiting for Golos processes to exit.'
{wait_pid_lines}
    Start-Sleep -Milliseconds 1200

    if (-not (Test-Path -LiteralPath $SourceDir)) {{ throw "Update source not found: $SourceDir" }}
    if (-not (Test-Path -LiteralPath (Join-Path $SourceDir 'Golos.exe'))) {{ throw "Update source does not contain Golos.exe." }}

    $BackupRoot = Join-Path $TargetDir 'updates\\backups'
    $BackupDir = Join-Path $BackupRoot $BackupName
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

    Write-UpdateLog 'Backing up current application files.'
    Get-ChildItem -LiteralPath $TargetDir -Force | Where-Object {{ $PreserveNames -notcontains $_.Name }} | ForEach-Object {{
        Move-Item -LiteralPath $_.FullName -Destination (Join-Path $BackupDir $_.Name) -Force
    }}

    Write-UpdateLog 'Copying new application files.'
    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {{
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetDir $_.Name) -Recurse -Force
    }}

    $ExePath = Join-Path $TargetDir 'Golos.exe'
    Write-UpdateLog 'Starting updated Golos.'
    Start-Process -FilePath $ExePath -ArgumentList @('--config', $ConfigPath) -WorkingDirectory $TargetDir -WindowStyle Hidden
    Write-UpdateLog 'Update completed.'
}} catch {{
    Write-UpdateLog ("Update failed: " + $_.Exception.Message)
    $BackupDir = Join-Path (Join-Path $TargetDir 'updates\\backups') $BackupName
    if (Test-Path -LiteralPath $BackupDir) {{
        try {{
            Write-UpdateLog 'Restoring previous application files.'
            Get-ChildItem -LiteralPath $TargetDir -Force | Where-Object {{ $PreserveNames -notcontains $_.Name }} | ForEach-Object {{
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
            }}
            Get-ChildItem -LiteralPath $BackupDir -Force | ForEach-Object {{
                Move-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetDir $_.Name) -Force
            }}
            $RestoredExe = Join-Path $TargetDir 'Golos.exe'
            if (Test-Path -LiteralPath $RestoredExe) {{
                Start-Process -FilePath $RestoredExe -ArgumentList @('--config', $ConfigPath) -WorkingDirectory $TargetDir -WindowStyle Hidden
            }}
        }} catch {{
            Write-UpdateLog ("Restore failed: " + $_.Exception.Message)
            $BackupExe = Join-Path $BackupDir 'Golos.exe'
            if (Test-Path -LiteralPath $BackupExe) {{
                Start-Process -FilePath $BackupExe -ArgumentList @('--config', $ConfigPath) -WorkingDirectory $BackupDir -WindowStyle Hidden
            }}
        }}
    }}
    exit 1
}}
"""
