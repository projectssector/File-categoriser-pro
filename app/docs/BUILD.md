# Build the Windows app and installer

Run all commands in this guide from the `app` folder (`cd app`).

The release build has two steps:

1. **PyInstaller** turns the Python app into the folder `dist\FileCategorizer\`.
2. **Inno Setup 6** wraps that folder in `dist\FileCategorizer-Setup-1.0.0.exe`.

## Prerequisites

- Windows 10/11 64-bit
- Python 3.12 (64-bit) from <https://python.org>
- Inno Setup 6 from <https://jrsoftware.org/isdl.php>
- Git (optional)

PyTorch is installed from PyPI as the CPU build. You do not need CUDA.

## 1. Set up the environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes PySide6, PyInstaller and the test tools.

## 2. Smoke test from source

```powershell
copy config\config.example.yaml config\config.yaml
python run_gui.py
```

Close the app when the window appears.

## 3. Build the exe

```powershell
python -m PyInstaller FileCategorizer.spec --noconfirm --clean
```

Output: `dist\FileCategorizer\FileCategorizer.exe` and its `_internal\`
folder (about 1 GB total).

The spec bundles the PySide6 GUI, open_clip, transformers, imagehash,
pytesseract and openpyxl. Model weights are **not** bundled; they download on
first run.

## 4. Build the installer

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" FileCategorizer.iss
```

If Inno Setup is installed elsewhere:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" FileCategorizer.iss
```

Output: `dist\FileCategorizer-Setup-1.0.0.exe`.

## 5. Verify

Install silently into a test folder, launch, then uninstall:

```powershell
$setup = "dist\FileCategorizer-Setup-1.0.0.exe"
$dir = "$env:TEMP\fc_test"
Start-Process $setup "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOICONS /DIR=`"$dir`"" -Wait
Start-Process "$dir\FileCategorizer.exe"
```

Close the app, then run `"$dir\unins000.exe" /VERYSILENT`.

Record the checksum for the release:

```powershell
Get-FileHash .\dist\FileCategorizer-Setup-1.0.0.exe -Algorithm SHA256
```

## Version bump checklist

Update all of these before a new release:

- `FileCategorizer.iss` -> `MyAppVersion`
- `pyproject.toml` -> `version`
- `src\file_categorizer\__init__.py` -> `__version__`
- `..\version_info.txt` -> `filevers` / `prodvers` / strings
- `..\README.md` and `..\INSTALL.txt` download filenames
- `RELEASE_NOTES.md` and `AUTHENTIC_CODE.txt`

## Notes

- The current build is **CPU-only**. A CUDA build needs a CUDA-enabled torch
  wheel and a larger installer.
- The app is a PyInstaller one-folder build (`COLLECT` in the spec). This
  starts much faster than a one-file build because nothing is unpacked to a
  temp folder at launch.
- The first launch after installing is still slow while Windows scans the
  roughly 7,500 new files.
- The installer is per-user and does not require admin rights.
- Code signing is optional. Without a certificate, SmartScreen shows an
  unknown-publisher warning.
- UPX is disabled in `FileCategorizer.spec` to avoid antivirus false
  positives.
