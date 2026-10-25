# File Categorizer 1.0.0

First public Windows release.

## Install

1. Download `FileCategorizer-Setup-1.0.0.exe` below.
2. Run it. It installs for the current user, with no admin rights needed.
3. Launch **File Categorizer** from the Start Menu.
4. The first launch downloads the local AI models (about 700 MB total), so
   keep an internet connection on.

## Highlights

- Drag-and-drop GUI for images and videos
- Local CLIP classification with an optional Gemini fallback
- Learns from corrections and remembers custom categories
- NSFW detection with per-category folders
- Exact and perceptual duplicate detection
- OCR and metadata extraction (optional), plus spreadsheet export
- SQLite cache for fast repeat runs
- CPU-only build, no GPU setup required

## Notes and known limitations

- The installer is **not code-signed** yet. Windows SmartScreen may warn;
  choose **More info** > **Run anyway**.
- This build is CPU-only. Classification speed depends on your CPU.
- Internet is required on first launch to download the AI models. Later
  launches use the cached models.
- The app is packaged as a folder build for faster startup. The first launch
  after installing can take up to a minute while Windows scans the files;
  later launches usually take 10-20 seconds.
- Gemini is optional and only used if you add an API key in Settings.
- OCR requires Tesseract for Windows, which is not bundled. Everything else
  works without it.
- Windows 10/11 64-bit only.

## Verify the download

See `AUTHENTIC_CODE.txt` in the repository, or run:

```powershell
Get-FileHash .\FileCategorizer-Setup-1.0.0.exe -Algorithm SHA256
```

## Data locations

- Program files: `%LOCALAPPDATA%\Programs\FileCategorizer`
- Settings, config and database: `%USERPROFILE%\FileCategorizer`
- Cached models: `%USERPROFILE%\.cache`
