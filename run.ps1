$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv $VenvPath
    } else {
        python -m venv $VenvPath
    }
}

$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -r requirements.txt
& $PythonPath -m voice_input.app

