# Configuration reference

Paths in this guide are relative to the `app` folder.

The template is `config/config.example.yaml`. The installed app copies it to
`%USERPROFILE%\FileCategorizer\config\config.yaml` on first launch.

## Paths

| Key | Default | Meaning |
| --- | --- | --- |
| `paths.inbox` | `./inbox` | Folder scanned by the CLI |
| `paths.output` | `./output` | Destination root for sorted files |
| `paths.nsfw` | `./NSFW` | NSFW destination |
| `paths.ambiguous` | `./ambiguous` | Low-confidence destination |
| `paths.database` | `./data/cache.db` | SQLite cache |
| `paths.logs` | `./data/logs` | Log folder |

Relative paths are resolved from the app's working folder.

## Categories

```yaml
categories:
  anime:
    scan_for:
      - "distinct linework and cel-shading"
      - "stylized or exaggerated eyes"
```

Each category is a name plus short visual clues used by CLIP. Add, rename or
remove categories here or in the GUI. Custom categories are also stored in
`data/categories.json`.

## Models

| Key | Default | Meaning |
| --- | --- | --- |
| `models.prefilter.type` | `clip` | Local prefilter |
| `models.prefilter.model` | `ViT-B-32` | CLIP model name |
| `models.prefilter.pretrained` | `laion2b_s34b_b79k` | CLIP weights |
| `models.prefilter.confidence_threshold` | `0.75` | Below this, use Gemini |
| `models.deep.type` | `gemini` | Fallback type |
| `models.deep.model` | `gemini-2.5-flash` | Preferred Gemini model |
| `models.nsfw.type` | `clip_nsfw` | NSFW classifier |
| `models.nsfw.threshold` | `0.85` | NSFW cutoff |
| `models.nsfw.classify` | `true` | Classify explicit files too |
| `models.nsfw.subfolder` | `true` | File under `NSFW/<category>/` |

The app auto-detects a usable Gemini model for your key, so a retired model
name will not break a run.

## Feedback and learning

| Key | Default | Meaning |
| --- | --- | --- |
| `feedback.confidence_threshold` | `0.75` | Review threshold |
| `feedback.learn_patterns` | `true` | Learn from corrections |
| `feedback.max_review_batch` | `50` | Review batch size |

## Video

| Key | Default | Meaning |
| --- | --- | --- |
| `video.frame_positions` | `[0.1, 0.5, 0.9]` | Frames sampled |
| `video.output_format` | `composite` | `composite` or `gif` |
| `video.max_duration_sec` | `120` | Max processed duration |

## Metadata and export

| Key | Default | Meaning |
| --- | --- | --- |
| `metadata.enabled` | `true` | Master switch |
| `ocr.enabled` | `true` | OCR on/off |
| `ocr.backend` | `tesseract` | `tesseract` or `paddle` |
| `ocr.lang` | `eng` | Tesseract language |
| `extraction.backend` | `gemini` | `gemini` or `none` |
| `extraction.model` | `gemini-2.5-flash` | VLM model |
| `dedupe.exact` | `true` | Hash duplicates |
| `dedupe.perceptual` | `true` | Perceptual duplicates |
| `dedupe.phash_threshold` | `6` | Lower is stricter |
| `spreadsheet.workbook_path` | `output/metadata.xlsx` | Export path |
| `spreadsheet.auto_export` | `false` | Export after every file |
| `spreadsheet.export_after_index` | `true` | Export after a batch |

## Enrichment

| Key | Default | Meaning |
| --- | --- | --- |
| `enrichment.youtube` | `true` | YouTube oEmbed (no key) |
| `enrichment.tmdb` | `true` | Needs `TMDB_API_KEY` |
| `enrichment.anilist` | `true` | AniList GraphQL (no key) |
| `enrichment.opengraph` | `true` | Page title/description |
| `enrichment.account_search` | `false` | Can cost API budget |

## Environment variables

| Variable | Meaning |
| --- | --- |
| `GEMINI_API_KEY` | Gemini API key (optional) |
| `TMDB_API_KEY` | TMDB enrichment (optional) |
| `LOG_LEVEL` | Logging level, default `INFO` |

In the installed app, the Gemini key can be saved in Settings instead of an
environment variable.
