# Run from source

Most Windows users should install the release instead. Use this guide for
development or debugging.

## Prerequisites

- Python 3.10 or newer (3.12 recommended)
- Windows, macOS or Linux
- A Gemini API key (optional)

## 1. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

Everything, including the GUI and test tools:

```powershell
pip install -r requirements-dev.txt
```

Runtime only:

```powershell
pip install -r requirements.txt
```

## 3. Configure

```powershell
copy config\config.example.yaml config\config.yaml
copy .env.example .env
```

Edit `config\config.yaml` for your folders and categories. Put a Gemini key
in `.env` or in the app's Settings window.

## 4. Run the GUI

```powershell
python run_gui.py
```

The app creates its runtime files next to the source folder when run this
way:

- `config\config.yaml`
- `data\cache.db`, `data\categories.json`, `data\settings.json`, `data\logs`
- `output\` for sorted files

## 5. Run the CLI

```powershell
python -m file_categorizer scan .\inbox --dry-run
python -m file_categorizer scan .\inbox
python -m file_categorizer review
python -m file_categorizer export
python -m file_categorizer stats
```

## 6. Run tests

```powershell
pytest -q
ruff check src tests
```

## Optional dependencies

- **Tesseract** for OCR: <https://github.com/UB-Mannheim/tesseract/wiki>
- **TMDB key** for movie/TV enrichment: set `TMDB_API_KEY` in the environment

The app degrades gracefully when these are missing.

## Build the installer

See [BUILD.md](BUILD.md).
