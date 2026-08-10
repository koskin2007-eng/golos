param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonPath)) {
    throw "Python venv not found. Run .\run.ps1 first."
}

$Version = (& $PythonPath -c "from voice_input.version import APP_VERSION; print(APP_VERSION)").Trim()
$Tag = "v$Version"
$Repository = "koskin2007-eng/golos"

if (-not $SkipBuild) {
    & (Join-Path $ProjectRoot "build_exe.ps1")
}

$AppDir = Join-Path $ProjectRoot "dist\Golos"
if (-not (Test-Path $AppDir)) {
    throw "Build output not found: $AppDir"
}

$ResolvedAppDir = [System.IO.Path]::GetFullPath($AppDir)
$RuntimeArtifacts = @("config.yaml", ".env", ".env.local", "logs", "diagnostics", "temp", "models")
foreach ($Name in $RuntimeArtifacts) {
    $Target = Join-Path $AppDir $Name
    if (-not (Test-Path $Target)) {
        continue
    }
    $ResolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if (-not $ResolvedTarget.StartsWith($ResolvedAppDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside app dir: $ResolvedTarget"
    }
    Remove-Item -LiteralPath $Target -Recurse -Force
}

$ReleaseRoot = Join-Path $ProjectRoot "dist\release"
$ReleaseDir = Join-Path $ReleaseRoot $Tag
$ResolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$ResolvedReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$ResolvedReleaseDir = [System.IO.Path]::GetFullPath($ReleaseDir)
if (-not $ResolvedReleaseDir.StartsWith($ResolvedProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write release outside project root: $ResolvedReleaseDir"
}

if (Test-Path $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
}
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

$ZipPath = Join-Path $ReleaseDir "Golos-win64.zip"
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force

$Hash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
$ShaPath = Join-Path $ReleaseDir "Golos-win64.sha256"
"$Hash  Golos-win64.zip" | Set-Content -Path $ShaPath -Encoding UTF8

$DownloadUrl = "https://github.com/$Repository/releases/download/$Tag/Golos-win64.zip"
$LatestPath = Join-Path $ReleaseDir "latest.json"
$Latest = [ordered]@{
    app = "Golos"
    version = $Version
    tag = $Tag
    platform = "windows-x64"
    asset = "Golos-win64.zip"
    sha256 = $Hash
    url = $DownloadUrl
}
$Latest | ConvertTo-Json -Depth 4 | Set-Content -Path $LatestPath -Encoding UTF8

Write-Host "Release assets:"
Write-Host "  $ZipPath"
Write-Host "  $ShaPath"
Write-Host "  $LatestPath"
