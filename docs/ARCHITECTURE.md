# Architecture

File Categorizer is a local-first desktop app. SQLite is the source of truth;
the Excel workbook is an export-only report.

## Project layout

```text
file-categorizer/
├── README.md
├── INSTALL.txt
├── LICENSE
├── SECURITY.md
├── RELEASE_NOTES.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── run_gui.py                    # GUI entry point
├── FileCategorizer.spec          # PyInstaller build
├── FileCategorizer.iss           # Inno Setup installer
├── version_info.txt              # Windows exe metadata
├── app_icon.ico
├── config/
│   └── config.example.yaml
├── src/file_categorizer/
│   ├── __main__.py               # CLI entry point
│   ├── cli.py
│   ├── gui.py                    # PySide6 GUI
│   ├── core/
│   │   ├── classifier.py         # CLIP + Gemini classification
│   │   ├── pipeline.py           # file move / dry-run orchestration
│   │   ├── config_loader.py
│   │   ├── db.py                 # cache, corrections, patterns, tags
│   │   ├── hasher.py
│   │   ├── video.py
│   │   ├── feedback.py
│   │   ├── owner_hint.py
│   │   ├── metadata_db.py        # meta_* tables
│   │   ├── metadata_pipeline.py  # wraps the file pipeline
│   │   ├── ocr.py                # Tesseract (optional)
│   │   ├── extractor.py          # Gemini VLM (optional)
│   │   ├── entities.py
│   │   ├── enrichment.py         # OpenGraph / YouTube / AniList / TMDB
│   │   ├── dedupe.py             # exact + perceptual + entity dedupe
│   │   ├── learning.py           # field corrections and patterns
│   │   ├── spreadsheet.py        # openpyxl export
│   │   ├── categories.py
│   │   ├── duplicates.py
│   │   ├── image_info.py
│   │   ├── gemini_resolver.py
│   │   ├── guidelines.py
│   │   └── report.py
│   ├── models/
│   │   ├── clip_model.py
│   │   ├── gemini_model.py
│   │   └── nsfw_model.py
│   └── utils/
│       ├── logger.py
│       └── paths.py
├── tests/
├── docs/
└── release/                      # local only; installer for GitHub Releases
```

## Processing flow

1. Files enter through drag-and-drop in the GUI or `scan` on the CLI.
2. NSFW check runs first. Explicit files are still categorized and filed
   under `NSFW/<category>/`.
3. CLIP classifies against the category list locally.
4. If confidence is below the threshold, the optional Gemini fallback runs.
5. Owner hints and past corrections influence the result.
6. The file is stored in the cache by hash, then moved (or previewed in a
   dry run) to `output/<category>/`.
7. The metadata layer optionally runs OCR, VLM extraction, entity enrichment
   and duplicate checks, storing results in `meta_*` tables.
8. The spreadsheet layer exports the SQLite data to `output/metadata.xlsx`.

## Runtime locations

- **Installed app:** `%LOCALAPPDATA%\Programs\FileCategorizer`
- **User data (installed):** `%USERPROFILE%\FileCategorizer`
- **Source runs:** relative to the project folder (`config\`, `data\`,
  `output\`)

## Packaging

- `FileCategorizer.spec` builds a one-folder, windowed app with PyInstaller.
- `FileCategorizer.iss` builds a per-user installer with Inno Setup 6.
- Model weights are not bundled; they are downloaded and cached on first run.
- The release installer is not code-signed. See `docs/BUILD.md`.
