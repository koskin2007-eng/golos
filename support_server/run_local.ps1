$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    python -m venv $venv
}

& $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
& $python -m uvicorn support_server.main:app --host 127.0.0.1 --port 8765
