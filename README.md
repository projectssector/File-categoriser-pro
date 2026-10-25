# File Categorizer

A local-first, self-learning file organizer for Windows. Drop in a folder of
images and videos and the app sorts them into categories, flags duplicates,
reads on-screen text and metadata, and exports everything to a spreadsheet.
It learns from your corrections, so it gets better the more you use it.

No Python installation is needed for the Windows app.

## Download and install

1. Open the [latest release](../../releases/latest).
2. Download **`FileCategorizer-Setup-1.0.0.exe`** (about 257 MB).
3. Run the installer. It installs for the current user only, so **no admin
   rights are required**.
4. Launch **File Categorizer** from the Start Menu.

See [INSTALL.txt](INSTALL.txt) if you prefer plain-text instructions.

> Windows SmartScreen may warn that the installer is from an unknown
> publisher because it is not code-signed yet. Click **More info** >
> **Run anyway**.

### First launch

- The first launch downloads the local AI models (about 700 MB total). Keep
  an internet connection on for a few minutes. Later launches use the cached
  models and start faster.
- A Gemini API key is **optional**. Add one in **Settings** if you want the
  AI fallback for difficult files. It is optional; the app works offline
  without it.
- Tesseract OCR is optional. Install it only if you want text extraction
  from screenshots. See [Optional extras](#optional-extras).

## Features

- Drag-and-drop GUI with categories, tags, progress, reports and review
- Local CLIP classification, with optional Gemini fallback for hard cases
- Learns from your corrections and remembers your custom categories
- NSFW detection with per-category folders
- Exact and perceptual duplicate detection
- OCR and metadata extraction (optional), with spreadsheet export
- SQLite cache so repeated runs are fast
- CPU-only build: no CUDA or GPU setup required

## Where your data is stored

| What | Location |
| --- | --- |
| Program files | `%LOCALAPPDATA%\Programs\FileCategorizer` |
| Settings, config, database, logs | `%USERPROFILE%\FileCategorizer` |
| Downloaded AI models | `%USERPROFILE%\.cache` |

Everything stays on your computer. Gemini is only contacted if you add an API
key and the local classifier is not confident enough.

To completely reset the app, uninstall it and delete
`%USERPROFILE%\FileCategorizer`.

## System requirements

- Windows 10 or Windows 11, 64-bit
- About 2-3 GB of free disk space (app, cached models and scratch space)
- Internet connection for the first launch (model download)

## Optional extras

- **Gemini API key** (AI fallback): create one at
  <https://aistudio.google.com/apikey>, then paste it into **Settings** in the
  app. It is stored locally in `%USERPROFILE%\FileCategorizer\data\settings.json`.
- **Tesseract OCR** (screenshot text extraction): install the Windows build
  from <https://github.com/UB-Mannheim/tesseract/wiki>. The app detects it
  automatically. Without it, OCR is skipped and everything else still works.
- **TMDB API key** (movie/TV enrichment): set the `TMDB_API_KEY` environment
  variable before launching the app.

## Troubleshooting

**Windows blocked the installer or shows SmartScreen**
The installer is not code-signed. Choose **More info** > **Run anyway**. If
your browser removed the file, download it again from the Releases page.

**The app takes a long time to open the first time**
Windows scans the newly installed files and the app downloads the AI models on
first run. This can take a minute or two. Later launches usually open in
10-20 seconds.

**Model download fails**
Check your firewall, proxy or antivirus. The model is fetched from Hugging
Face on first launch.

**Antivirus quarantines the app**
The app is unsigned, and some antivirus tools flag unsigned PyInstaller
programs as false positives. Add an exclusion for the install folder, or build
the app yourself from source.

**OCR is not working**
Install Tesseract (see above) and restart the app.

**The app will not start**
Uninstall it, delete `%USERPROFILE%\FileCategorizer`, and install again. If it
still fails, run from source (below) to see the error output.

## Run from source

For development or if you prefer Python:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements-dev.txt
copy config\config.example.yaml config\config.yaml
copy .env.example .env
python run_gui.py
```

Command line:

```powershell
python -m file_categorizer scan .\inbox --dry-run
python -m file_categorizer scan .\inbox
python -m file_categorizer export
```

See [docs/SETUP.md](docs/SETUP.md) for details.

## Build the Windows installer

The installer is built with PyInstaller and Inno Setup 6. See
[docs/BUILD.md](docs/BUILD.md).

```powershell
pip install -r requirements-dev.txt
python -m PyInstaller FileCategorizer.spec --noconfirm --clean
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" FileCategorizer.iss
```

The result is `dist\FileCategorizer-Setup-1.0.0.exe`.

## How it works

See [HOW_IT_WORKS.txt](HOW_IT_WORKS.txt) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

- [Install guide](INSTALL.txt)
- [Run from source](docs/SETUP.md)
- [Build the installer](docs/BUILD.md)
- [Configuration reference](docs/CONFIG.md)
- [Architecture](docs/ARCHITECTURE.md)

## License

MIT. See [LICENSE](LICENSE).

## Security

Never commit your `.env`, `data/settings.json` or any API key. See
[SECURITY.md](SECURITY.md).
