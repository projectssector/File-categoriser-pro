# Build script for File Categorizer Windows installer
# Requires: Python 3.12+, PyInstaller, Inno Setup 6 (ISCC.exe)
#
# Usage:
#   .\build.ps1
#
# Output:
#   dist/FileCategorizer-Setup-1.0.0.exe

$ErrorActionPreference = 'Stop'
$APP_DIR = $PSScriptRoot
$SPEC_FILE = Join-Path $APP_DIR 'FileCategorizer.spec'
$ISS_FILE = Join-Path $APP_DIR 'FileCategorizer.iss'
$VCRedist_URL = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
$VCRedist_PATH = Join-Path $APP_DIR 'vc_redist.x64.exe'

Write-Host "=== File Categorizer Build Script ===" -ForegroundColor Cyan

# 1. Verify Python
Write-Host "`n[1/5] Checking Python..." -ForegroundColor Yellow
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found on PATH. Install Python 3.12+ first."
    exit 1
}
python --version

# 2. Install dependencies
Write-Host "`n[2/5] Installing Python dependencies..." -ForegroundColor Yellow
pip install --upgrade pip
pip install -r "$APP_DIR\requirements-dev.txt"
pip install pyinstaller

# 3. Download VC++ Redistributable (required by PyInstaller binaries)
Write-Host "`n[3/5] Downloading VC++ Redistributable..." -ForegroundColor Yellow
if (!(Test-Path $VCRedist_PATH)) {
    Invoke-WebRequest -Uri $VCRedist_URL -OutFile $VCRedist_PATH
    Write-Host "Downloaded vc_redist.x64.exe" -ForegroundColor Green
} else {
    Write-Host "vc_redist.x64.exe already present, skipping download." -ForegroundColor Green
}

# 4. Build standalone EXE with PyInstaller
Write-Host "`n[4/5] Building EXE with PyInstaller..." -ForegroundColor Yellow
Set-Location $APP_DIR
python -m PyInstaller $SPEC_FILE --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}
Write-Host "EXE built in dist\FileCategorizer\" -ForegroundColor Green

# 5. Build installer with Inno Setup
Write-Host "`n[5/5] Building installer with Inno Setup..." -ForegroundColor Yellow
$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
if (!(Test-Path $iscc)) {
    Write-Error "Inno Setup not found at $iscc. Install Inno Setup 6 first."
    exit 1
}
& $iscc $ISS_FILE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup build failed."
    exit 1
}

Write-Host "`n=== Build complete! ===" -ForegroundColor Cyan
Write-Host "Installer: $APP_DIR\dist\FileCategorizer-Setup-1.0.0.exe" -ForegroundColor Green