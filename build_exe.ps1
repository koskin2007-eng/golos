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

$Version = (& $PythonPath -c "from voice_input.version import APP_VERSION; print(APP_VERSION)").Trim()
Write-Host "Building Golos version $Version"

$AssetsPath = Join-Path $ProjectRoot "voice_input\assets"
$IconPath = Join-Path $AssetsPath "golos.ico"

& $PythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --noconsole `
    --name Golos `
    --icon $IconPath `
    --distpath dist `
    --workpath build `
    --specpath build `
    --add-data "$AssetsPath;voice_input\assets" `
    --collect-all faster_whisper `
    voice_input\app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Done. EXE folder: $ProjectRoot\dist\Golos"
