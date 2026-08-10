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

# Tcl/Tk cannot initialize from a Windows user path with Cyrillic characters in
# some Python distributions. PyInstaller also excludes tkinter in that case.
# Copy only the runtime scripts to an ASCII-only project path for analysis.
$VenvConfigPath = Join-Path $VenvPath "pyvenv.cfg"
$PythonHomeLine = Get-Content -LiteralPath $VenvConfigPath -Encoding UTF8 | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $PythonHomeLine) {
    throw "Python home not found in $VenvConfigPath"
}
$PythonHome = ($PythonHomeLine -split '=', 2)[1].Trim()
$TclSource = Join-Path $PythonHome "tcl\tcl8.6"
$TkSource = Join-Path $PythonHome "tcl\tk8.6"
$TkBuildRoot = Join-Path $ProjectRoot ".build-runtime"
$TclBuildPath = Join-Path $TkBuildRoot "tcl8.6"
$TkBuildPath = Join-Path $TkBuildRoot "tk8.6"
if (-not (Test-Path (Join-Path $TclSource "init.tcl")) -or -not (Test-Path (Join-Path $TkSource "tk.tcl"))) {
    throw "Tcl/Tk runtime not found under $PythonHome"
}
New-Item -ItemType Directory -Path $TkBuildRoot -Force | Out-Null
Copy-Item -LiteralPath $TclSource -Destination $TkBuildRoot -Recurse -Force
Copy-Item -LiteralPath $TkSource -Destination $TkBuildRoot -Recurse -Force
$env:TCL_LIBRARY = $TclBuildPath
$env:TK_LIBRARY = $TkBuildPath

# Fail early if the copied runtime cannot initialize.
& $PythonPath -c "import tkinter; root = tkinter.Tcl(); print('Tcl/Tk', root.eval('info patchlevel'))"
if ($LASTEXITCODE -ne 0) {
    throw "Tcl/Tk runtime validation failed"
}

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
