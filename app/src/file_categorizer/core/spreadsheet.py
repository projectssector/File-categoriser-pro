# File: src/file_categorizer/core/spreadsheet.py
"""
spreadsheet.py
==============

PURPOSE
-------
Exports everything stored in MetadataDatabase into a single Excel workbook
with multiple sheets.

Sheets:
  Master            one row per file (including local image/EXIF data)
  Image_Info        the same image facts in a focused sheet
  Duplicates        exact + perceptual duplicate groups with keep suggestions
  Anime             unique anime titles
  Movies_TV         unique movie / TV titles
  YouTube           unique video titles + channels
  Social_Accounts   unique accounts
  Websites          unique websites / URLs
  Songs             unique songs
  Unknown_Review    files with needs_review=1

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy into src/file_categorizer/core/.
2. From GUI/CLI:
       from .spreadsheet import export_workbook
       export_workbook(mdb, "output/metadata.xlsx")
3. Re-running overwrites the workbook from DB. Excel is a report, not a
   source of truth.

INSTALL
-------
    pip install openpyxl

NOTES FOR OTHER AI AGENTS
-------------------------
- DB is the source of truth. This module only reads.
- To add a column, update BOTH the extraction field list (extractor.py)
  and the per-sheet column list below. They must stay in sync.
- Missing cells are written as empty strings, not None, so Excel displays
  cleanly.
- Hyperlinks: URL column is written as a clickable hyperlink.
- Do not sort rows by anything other than first_seen DESC in Master.
- If a file appears in more than one entity, it can appear in more than
  one entity sheet. That is intentional.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .metadata_db import MetadataDatabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

MASTER_COLUMNS = [
    "file_id", "file_path", "file_hash", "moved_to", "renamed_to",
    "category", "subcategory", "platform",
    "file_size", "image_width", "image_height", "image_format", "image_mode",
    "taken_date", "camera_make", "camera_model", "lens_model", "orientation",
    "gps_latitude", "gps_longitude", "phash",
    "duplicate_status", "duplicate_of", "duplicate_group",
    "account_name", "display_name", "source_name", "title_from_source", "sitelink",
    "video_title",
    "anime_name", "manga_name", "movie_tv_name",
    "website_name", "url",
    "song_name", "artist",
    "comment_text", "extracted_text", "evidence",
    "confidence", "model_used",
    "needs_review", "first_seen", "last_updated", "notes",
]

IMAGE_INFO_COLUMNS = [
    "file_id", "file_path", "category",
    "file_size", "image_width", "image_height", "image_format", "image_mode",
    "taken_date", "camera_make", "camera_model", "lens_model", "orientation",
    "gps_latitude", "gps_longitude", "phash",
    "duplicate_status", "duplicate_of", "duplicate_group",
]

DUPLICATE_COLUMNS = [
    "group", "kind", "keep_file", "file_path", "file_hash", "file_size",
    "similarity", "group_files", "group_reclaimable_bytes", "status",
]

ENTITY_SHEET_COLUMNS = {
    "Anime":           ["anime_name", "file_id", "file_path",
                        "account_name", "platform", "url",
                        "title_from_source", "sitelink", "source_name",
                        "confidence", "notes"],
    "Movies_TV":       ["movie_tv_name", "file_id", "file_path",
                        "account_name", "platform", "url",
                        "title_from_source", "sitelink", "source_name",
                        "confidence", "notes"],
    "YouTube":         ["video_title", "account_name", "display_name",
                        "url", "file_id", "file_path",
                        "channel", "sitelink",
                        "confidence", "notes"],
    "Social_Accounts": ["account_name", "display_name", "platform",
                        "bio_summary", "content_type", "url",
                        "file_id", "file_path",
                        "source_name", "sitelink",
                        "confidence", "notes"],
    "Websites":        ["website_name", "url", "account_name",
                        "file_id", "file_path",
                        "sitelink", "source_name",
                        "confidence", "notes"],
    "Songs":           ["song_name", "artist", "source", "evidence",
                        "file_id", "file_path", "url", "sitelink",
                        "confidence", "notes"],
    "Manga":           ["manga_name", "file_id", "file_path",
                        "account_name", "platform", "url",
                        "title_from_source", "sitelink", "source_name",
                        "confidence", "notes"],
    "Unknown_Review":  ["file_id", "file_path", "reason_for_review",
                        "extracted_text", "comment_text", "candidate_fields",
                        "account_name", "website_name", "url",
                        "title_from_source", "sitelink",
                        "confidence", "notes"],
}

ENTITY_TYPE_TO_SHEET = {
    "anime":    "Anime",
    "manga":    "Manga",
    "movie_tv": "Movies_TV",
    "account":  "Social_Accounts",
    "website":  "Websites",
    "song":     "Songs",
    "url":      "Websites",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _f(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _fields_for(mdb: MetadataDatabase, file_hash: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in mdb.get_fields(file_hash):
        name = row["field_name"]
        value = row["field_value"]
        # keep highest confidence per field
        if name not in out:
            out[name] = _s(value)
    return out


def _duplicate_index(groups: list[Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for group in groups:
        for f in group.files:
            if f.file_hash in out:
                continue
            out[f.file_hash] = {
                "duplicate_status": group.kind,
                "duplicate_of": group.keep_path,
                "duplicate_group": group.group_id,
            }
    return out


def _build_master_row(
    mdb: MetadataDatabase,
    frow: Any,
    duplicate_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    file_hash = frow["file_hash"]
    fields = _fields_for(mdb, file_hash)
    duplicate = (duplicate_map or {}).get(file_hash, {})
    return {
        "file_id":        file_hash[:12],
        "file_path":      frow["file_path"],
        "file_hash":      file_hash,
        "moved_to":       frow["moved_to"] or "",
        "renamed_to":     fields.get("renamed_to", "") or "",
        "category":       frow["category"] or "",
        "subcategory":    frow["subcategory"] or "",
        "platform":       frow["platform"] or fields.get("platform", ""),
        "file_size":      fields.get("file_size", ""),
        "image_width":    fields.get("image_width", ""),
        "image_height":   fields.get("image_height", ""),
        "image_format":   fields.get("image_format", ""),
        "image_mode":     fields.get("image_mode", ""),
        "taken_date":     fields.get("taken_date", ""),
        "camera_make":    fields.get("camera_make", ""),
        "camera_model":   fields.get("camera_model", ""),
        "lens_model":     fields.get("lens_model", ""),
        "orientation":    fields.get("orientation", ""),
        "gps_latitude":   fields.get("gps_latitude", ""),
        "gps_longitude":  fields.get("gps_longitude", ""),
        "phash":          fields.get("phash", ""),
        "duplicate_status": duplicate.get("duplicate_status", ""),
        "duplicate_of":   duplicate.get("duplicate_of", ""),
        "duplicate_group": duplicate.get("duplicate_group", ""),
        "account_name":   fields.get("account_name", ""),
        "display_name":   fields.get("display_name", ""),
        "source_name":    fields.get("source_name", "") or fields.get("site_name", ""),
        "title_from_source": fields.get("title_from_source", "") or fields.get("title", ""),
        "sitelink":       fields.get("sitelink", "") or fields.get("site_link", "") or fields.get("url", ""),
        "video_title":    fields.get("video_title", ""),
        "anime_name":     fields.get("anime_name", ""),
        "manga_name":     fields.get("manga_name", ""),
        "movie_tv_name":  fields.get("movie_tv_name", ""),
        "website_name":   fields.get("website_name", ""),
        "url":            fields.get("url", ""),
        "song_name":      fields.get("song_name", ""),
        "artist":         fields.get("artist", ""),
        "comment_text":   fields.get("comment_text", ""),
        "extracted_text": fields.get("extracted_text", ""),
        "evidence":       fields.get("evidence", ""),
        "confidence":     _f(fields.get("confidence", 0.0)),
        "model_used":     fields.get("model_used", ""),
        "needs_review":   bool(frow["needs_review"]),
        "first_seen":     frow["first_seen"],
        "last_updated":   frow["last_updated"],
        "notes":          frow["notes"] or "",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_workbook(
    mdb: MetadataDatabase,
    workbook_path: str | Path = "output/metadata.xlsx",
) -> Path:
    """
    Build (or overwrite) the workbook from the database.
    Returns the path written.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        from openpyxl.utils import get_column_letter
    except Exception as e:
        raise RuntimeError(
            "openpyxl is required for spreadsheet export. "
            "Install with: pip install openpyxl"
        ) from e

    out_path = Path(workbook_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    try:
        from .duplicates import scan_duplicates
        groups = scan_duplicates(mdb)
    except Exception as exc:
        logger.warning("duplicate scan skipped during export: %s", exc)
        groups = []
    duplicate_map = _duplicate_index(groups)

    # ---------------- Master ----------------
    ws = wb.active
    ws.title = "Master"
    ws.append(MASTER_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for frow in mdb.all_files():
        row = _build_master_row(mdb, frow, duplicate_map)
        ws.append([row.get(c, "") for c in MASTER_COLUMNS])
        # Hyperlink URL
        url_idx = MASTER_COLUMNS.index("url") + 1
        last_row = ws.max_row
        url_val = ws.cell(row=last_row, column=url_idx).value
        if url_val:
            c = ws.cell(row=last_row, column=url_idx)
            c.hyperlink = url_val
            c.font = Font(color="0000EE", underline="single")

    _autosize(ws, get_column_letter)

    # ---------------- Image_Info ----------------
    image_ws = wb.create_sheet(title="Image_Info")
    image_ws.append(IMAGE_INFO_COLUMNS)
    for cell in image_ws[1]:
        cell.font = Font(bold=True)
    for frow in mdb.all_files():
        row = _build_master_row(mdb, frow, duplicate_map)
        image_ws.append([row.get(c, "") for c in IMAGE_INFO_COLUMNS])
    _autosize(image_ws, get_column_letter)

    # ---------------- Duplicates ----------------
    dup_ws = wb.create_sheet(title="Duplicates")
    dup_ws.append(DUPLICATE_COLUMNS)
    for cell in dup_ws[1]:
        cell.font = Font(bold=True)
    for group in groups:
        for f in group.files:
            similarity = ""
            if f.similarity is not None:
                similarity = f"{f.similarity:.3f}"
            elif group.kind == "exact":
                similarity = "1.000"
            dup_ws.append([
                group.group_id,
                group.kind,
                group.keep_path,
                f.file_path,
                f.file_hash,
                f.file_size,
                similarity,
                len(group.files),
                group.reclaimable,
                "keep" if f.is_keep else "duplicate",
            ])
    _autosize(dup_ws, get_column_letter)

    # ---------------- Entity sheets ----------------
    for sheet_name, columns in ENTITY_SHEET_COLUMNS.items():
        ws2 = wb.create_sheet(title=sheet_name)
        ws2.append(columns)
        for cell in ws2[1]:
            cell.font = Font(bold=True)

        if sheet_name == "Unknown_Review":
            for frow in mdb.all_files():
                if not frow["needs_review"]:
                    continue
                fields = _fields_for(mdb, frow["file_hash"])
                ws2.append([
                    frow["file_hash"][:12],
                    frow["file_path"],
                    "needs review",
                    fields.get("extracted_text", ""),
                    fields.get("comment_text", ""),
                    "",
                    fields.get("account_name", ""),
                    fields.get("website_name", ""),
                    fields.get("url", "") or fields.get("sitelink", ""),
                    fields.get("title_from_source", "") or fields.get("anime_name", "") or fields.get("video_title", ""),
                    fields.get("sitelink", "") or fields.get("url", ""),
                    _f(fields.get("confidence", 0.0)),
                    frow["notes"] or "",
                ])
            _autosize(ws2, get_column_letter)
            continue

        # Map entity types to this sheet
        wanted_types = [t for t, s in ENTITY_TYPE_TO_SHEET.items() if s == sheet_name]
        for etype in wanted_types:
            for erow in mdb.all_entities(entity_type=etype):
                files = mdb.get_file_entities_files(erow["id"]) \
                    if hasattr(mdb, "get_file_entities_files") else []
                if not files:
                    # Add a single row without file context
                    row = _entity_row_without_file(sheet_name, erow)
                    ws2.append([row.get(c, "") for c in columns])
                    continue
                for f in files:
                    row = _entity_row_with_file(sheet_name, erow, f)
                    ws2.append([row.get(c, "") for c in columns])

        _autosize(ws2, get_column_letter)

    wb.save(out_path)
    sheet_count = len(wb.sheetnames)
    row_count = sum(ws.max_row for ws in wb.worksheets)
    mdb.log_export(str(out_path), sheet_count, row_count, notes="auto-export")
    logger.info("Wrote workbook %s (%d sheets, %d rows)",
                out_path, sheet_count, row_count)
    return out_path


def _entity_row_without_file(sheet_name: str, erow: Any) -> dict[str, Any]:
    return {
        "anime_name":     erow["entity_value"] if sheet_name == "Anime" else "",
        "manga_name":     erow["entity_value"] if sheet_name == "Manga" else "",
        "movie_tv_name":  erow["entity_value"] if sheet_name == "Movies_TV" else "",
        "video_title":    erow["display_name"] or erow["entity_value"]
                          if sheet_name == "YouTube" else "",
        "account_name":   erow["entity_value"]
                          if sheet_name in ("Social_Accounts",) else "",
        "display_name":   erow["display_name"] or "",
        "platform":       erow["platform"] or "",
        "bio_summary":    erow["bio_summary"] or "",
        "content_type":   erow["content_type"] or "",
        "website_name":   erow["entity_value"] if sheet_name == "Websites" else "",
        "url":            erow["url"] or "",
        "sitelink":       erow["url"] or "",
        "source_name":    erow["display_name"] or erow["entity_value"] or "",
        "title_from_source": erow["display_name"] or erow["entity_value"] or "",
        "channel":        erow["display_name"] or "",
        "song_name":      erow["entity_value"] if sheet_name == "Songs" else "",
        "artist":         "",
        "source":         "",
        "evidence":       "",
        "file_id":        "",
        "file_path":      "",
        "confidence":     _f(erow["confidence"]),
        "notes":          "",
        "reason_for_review": "",
        "extracted_text": "",
        "comment_text": "",
        "candidate_fields": "",
    }


def _entity_row_with_file(sheet_name: str, erow: Any, frow: Any) -> dict[str, Any]:
    base = _entity_row_without_file(sheet_name, erow)
    base["file_id"] = frow["file_hash"][:12]
    base["file_path"] = frow["file_path"]
    return base


def _autosize(ws, get_column_letter) -> None:
    for i, col in enumerate(ws.iter_cols(), start=1):
        max_len = 0
        for cell in col:
            v = cell.value
            if v is None:
                continue
            max_len = max(max_len, len(str(v)))
        ws.column_dimensions[get_column_letter(i)].width = min(max(12, max_len + 2), 60)