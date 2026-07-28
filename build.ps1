$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$DistRoot = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot "build"
$AppName = "VideoCodeDuplicateFinder"
$AppDir = Join-Path $DistRoot $AppName
$ZipPath = Join-Path $DistRoot "$AppName-v0.0.3-windows-x64.zip"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Create a virtual environment and install requirements.txt first."
}

if (-not (Test-Path -LiteralPath $PyInstaller)) {
    & $Python -m pip install "pyinstaller>=6.0"
}

if (Test-Path -LiteralPath $AppDir) {
    Remove-Item -LiteralPath $AppDir -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

& $PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --distpath $DistRoot `
    --workpath $BuildRoot `
    (Join-Path $ProjectRoot "main.py")

Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $AppDir
Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination $AppDir
Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md") -Destination $AppDir
Copy-Item -LiteralPath (Join-Path $ProjectRoot "CHANGELOG.md") -Destination $AppDir

Compress-Archive -Path $AppDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Build complete: $AppDir"
Write-Host "Release archive: $ZipPath"
Write-Host "FFmpeg is intentionally not bundled. Configure it from Settings."
