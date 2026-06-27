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
$ConfigPath = Join-Path $ProjectRoot "config.yaml"
& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -r requirements.txt

& $PythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --noconsole `
    --name VoiceInput `
    --distpath dist `
    --workpath build `
    --specpath build `
    --add-data "$ConfigPath;." `
    --collect-all faster_whisper `
    voice_input\app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Done. EXE folder: $ProjectRoot\dist\VoiceInput"
