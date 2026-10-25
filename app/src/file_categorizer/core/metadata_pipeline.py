# File: src/file_categorizer/core/metadata_pipeline.py
"""
metadata_pipeline.py
====================

PURPOSE
-------
Wraps the existing FilePipeline with the metadata extraction layer:
exact-duplicate guard -> classify/move -> local image/EXIF index -> OCR
-> VLM extraction -> entity parsing -> enrichment -> dedupe -> DB
-> spreadsheet row.

The existing FilePipeline still does NSFW + category classification + file
move. This module adds the metadata step right after classification and
before returning the result.

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
Option A (recommended): use this as a drop-in replacement in the GUI/CLI
    from .metadata_pipeline import MetadataPipeline
    pipe = MetadataPipeline(cfg, db, mdb, gemini_key)
    result = pipe.process(path, dry_run=..., user_tags=[...])
    # result now also contains "metadata_fields" and "metadata_entities"

Option B (minimal): keep FilePipeline and call this module afterwards
    result = file_pipeline.process(path, dry_run, user_tags)
    meta = metadata_extract_for_result(result, cfg, db, mdb, gemini_key)

The GUI worker and CLI both call .process() the same way; nothing else
needs to change in the existing code.

NOTES FOR OTHER AI AGENTS
-------------------------
- This class is intentionally a thin wrapper. Do not duplicate the
  classification cascade here; call the existing FilePipeline.
- Metadata extraction respects dry_run: fields are still written to the
  DB (so the review panel can show them), but the spreadsheet export
  does not auto-trigger unless cfg.spreadsheet["auto_export"] is true
  AND dry_run is false.
- If the extractor is unavailable (no API key), only OCR + entity dedupe
  run. That is fine; the review panel will simply have fewer fields.
- Do not add new DB columns here. Add them to metadata_db.py.
- This module owns the ordering:
    1. run OCR
    2. run extractor
    3. parse candidates
    4. dedupe check (exact + perceptual)
    5. upsert file row
    6. upsert fields
    7. upsert entities + links
    8. optional auto-export
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from .config_loader import Config
from .db import Database
from .metadata_db import (
    MetaEntity, MetaField, MetaFile, MetadataDatabase,
)
from .dedupe import check_duplicate, select_missing_fields
from .entities import parse_candidates
from .enrichment import enrich_entities
from .extractor import Extractor
from .image_info import collect_image_info
from .learning import apply_field_corrections, pattern_suggestion
from .ocr import run_ocr
from .pipeline import FilePipeline, load_image

logger = logging.getLogger(__name__)


class MetadataPipeline:
    def __init__(
        self,
        config: Config,
        db: Database,
        mdb: MetadataDatabase,
        gemini_key: str | None = None,
    ):
        self.cfg = config
        self.db = db
        self.mdb = mdb
        self.base = FilePipeline(config, db)

        meta_cfg = self.cfg.raw.get("metadata", {}) if hasattr(self.cfg, "raw") else {}
        ocr_cfg = self.cfg.raw.get("ocr", {}) if hasattr(self.cfg, "raw") else {}
        ex_cfg = self.cfg.raw.get("extraction", {}) if hasattr(self.cfg, "raw") else {}

        self.meta_enabled = bool(meta_cfg.get("enabled", True))
        self.ocr_cfg = ocr_cfg
        self.extractor = Extractor(ex_cfg, api_key=gemini_key)
        self.dedupe_cfg = self.cfg.raw.get("dedupe", {}) if hasattr(self.cfg, "raw") else {}

        self.mdb.init_schema()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def process(
        self,
        path: Path,
        dry_run: bool = False,
        user_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        path = Path(path)

        # Lap-style exact-duplicate guard.  This runs BEFORE FilePipeline moves
        # the file, so a byte-identical copy can never overwrite the copy that
        # is already in the output folder.  The duplicate stays where it is and
        # we simply record the extra location for the Duplicates report.
        pre_hash = _hash(path, fast=False) if self.meta_enabled and path.exists() else None
        if pre_hash:
            duplicate = self._exact_duplicate_result(pre_hash, path)
            if duplicate is not None:
                return duplicate

        result = self.base.process(path, dry_run=dry_run, user_tags=user_tags)
        if pre_hash:
            result["file_hash"] = pre_hash

        status = result.get("status")
        if status not in ("classified", "nsfw"):
            return result

        # Give explicit-content files a real category so they are still
        # reviewable and exported rather than being dropped.
        if status == "nsfw" and not result.get("tag"):
            result["tag"] = "NSFW"
            result.setdefault("model", "nsfw")

        if not self.meta_enabled:
            return result

        # Only run metadata on files that were classified or explicitly NSFW-logged.
        # FilePipeline.process() MOVES the file unless dry_run, so resolve a
        # readable path (the moved destination) before loading/hashing.
        read_path = Path(path)
        if not read_path.exists():
            moved = result.get("moved_to")
            if moved and Path(moved).exists():
                read_path = Path(moved)

        try:
            image = load_image(read_path)
        except Exception as e:
            logger.warning("metadata_pipeline: cannot load image %s: %s", read_path, e)
            return result

        if image is None:
            return result

        fields, entities = self._extract(read_path, image, result)
        result["metadata_fields"] = [
            {"field_name": f.field_name, "field_value": f.field_value,
             "source": f.source, "confidence": f.confidence}
            for f in fields
        ]
        result["metadata_entities"] = [
            {"entity_type": e.entity_type, "entity_value": e.entity_value}
            for e in entities
        ]

        if self.meta_auto_export() and not dry_run:
            try:
                from .spreadsheet import export_workbook
                wb = self.cfg.raw.get("spreadsheet", {}).get(
                    "workbook_path", "output/metadata.xlsx"
                )
                export_workbook(self.mdb, wb)
                result["metadata_export"] = wb
            except Exception as e:
                logger.warning("auto-export failed: %s", e)

        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def meta_auto_export(self) -> bool:
        sp = self.cfg.raw.get("spreadsheet", {}) if hasattr(self.cfg, "raw") else {}
        return bool(sp.get("auto_export", False))

    def _exact_duplicate_result(
        self, file_hash: str, path: Path
    ) -> dict[str, Any] | None:
        """Return a duplicate result if another path already has this hash."""
        other = self.mdb.find_location_by_hash(file_hash, exclude_path=str(path))
        prior = self.mdb.get_file(file_hash)
        prior_is_other_file = False
        if prior is not None:
            known_paths = {str(prior["file_path"])}
            if prior["moved_to"]:
                known_paths.add(str(prior["moved_to"]))
            prior_is_other_file = str(path) not in known_paths
        if other is None and not prior_is_other_file:
            return None

        stat = _stat(path)
        self.mdb.record_location(
            file_hash,
            str(path),
            original_path=str(path),
            file_size=stat[0],
            modified_at=stat[1],
        )
        keep_path = (
            str(other["file_path"]) if other is not None
            else (str(prior["file_path"]) if prior is not None else None)
        )
        tag = str(prior["category"]) if prior is not None and prior["category"] else None
        return {
            "path": str(path),
            "status": "duplicate",
            "tag": tag,
            "confidence": 1.0,
            "model": "dedupe",
            "file_hash": file_hash,
            "metadata_duplicate": {
                "is_duplicate": True,
                "reason": "exact",
                "duplicate_of": file_hash,
            },
            "duplicate_of_path": keep_path,
            "metadata_fields": [],
            "metadata_entities": [],
            "notes": "exact duplicate; left in place",
        }

    def _extract(
        self,
        read_path: Path,
        image: np.ndarray,
        base_result: dict[str, Any],
    ) -> tuple[list[MetaField], list[MetaEntity]]:
        file_hash = base_result.get("file_hash") or _hash(read_path, fast=True)
        base_result["file_hash"] = file_hash

        # --- dedupe (must run BEFORE any DB write) ----------------------
        dup = check_duplicate(file_hash, image, self.mdb, self.dedupe_cfg)
        base_result["metadata_duplicate"] = {
            "is_duplicate": dup.is_duplicate,
            "reason": dup.reason,
            "duplicate_of": dup.duplicate_of,
        }
        base_result["perceptual_hash"] = dup.phash
        if dup.is_duplicate:
            logger.info("Duplicate (%s) of %s", dup.reason, dup.duplicate_of)

        # Exact duplicate: the file is already fully recorded, so skip the
        # (paid) OCR + extraction work and only refresh the file row.
        if dup.exact_match_hash:
            record_path = Path(base_result.get("path") or read_path)
            image_fields = collect_image_info(
                read_path, image, phash=dup.phash, file_hash=file_hash
            )
            self._persist(file_hash, record_path, base_result, image_fields, [])
            return image_fields, []

        # --- OCR --------------------------------------------------------
        ocr_text = ""
        if self.ocr_cfg.get("enabled", True):
            ocr_text = run_ocr(image, self.ocr_cfg) or ""

        # --- VLM extraction --------------------------------------------
        candidates: dict[str, Any] = {}
        if self.extractor.available:
            candidates = self.extractor.extract(image, ocr_text) or {}

        # Always store OCR text as a field, even if empty
        if ocr_text:
            candidates.setdefault("extracted_text", {
                "value": ocr_text,
                "source": "ocr",
                "confidence": 0.9,
                "evidence": "OCR output",
            })

        # --- parse ------------------------------------------------------
        fields, entities = parse_candidates(file_hash, candidates)

        # --- enrichment (best-effort, cached, never fatal) --------------
        try:
            enrich_entities(entities, self.cfg, self.mdb)
        except Exception as e:
            logger.warning("enrichment skipped: %s", e)

        # --- "already recorded": only add fields we do not have yet -----
        if self.mdb.file_exists(file_hash):
            existing = self.mdb.get_field_names(file_hash)
            fields = select_missing_fields(fields, existing)

        # --- local image/EXIF index (always refresh) --------------------
        fields.extend(collect_image_info(
            read_path, image, phash=dup.phash, file_hash=file_hash
        ))

        # --- field-level learning (Phase 6) -----------------------------
        # Learned values always win, so they go in AFTER the missing-field
        # filter (a correction may legitimately override an existing value).
        fields, learned = apply_field_corrections(
            file_hash, fields, entities, self.mdb
        )
        if learned:
            base_result["metadata_learned"] = [f.field_name for f in learned]

        # --- entity -> category memory (suggestion only) ----------------
        suggestion = pattern_suggestion(self.db, entities)
        if suggestion:
            base_result["metadata_pattern_suggestion"] = {
                "category": suggestion[0],
                "weight": suggestion[1],
            }
            # The file was already moved under the classified tag, so a
            # memory that disagrees is surfaced for review, not force-moved.
            if suggestion[1] >= 2.0 and suggestion[0] != base_result.get("tag"):
                base_result["needs_review"] = True

        # --- persist ----------------------------------------------------
        record_path = Path(base_result.get("path") or read_path)
        self._persist(file_hash, record_path, base_result, fields, entities)
        return fields, entities

    def _persist(
        self,
        file_hash: str,
        path: Path,
        base_result: dict[str, Any],
        fields: list[MetaField],
        entities: list[MetaEntity],
    ) -> None:
        dup_info = base_result.get("metadata_duplicate") or {}
        needs_review = (
            bool(base_result.get("confidence", 1.0) < 0.5)
            or dup_info.get("reason") == "perceptual"
            or bool(base_result.get("needs_review"))
        )
        is_nsfw = bool(base_result.get("nsfw")) or base_result.get("status") == "nsfw"
        mf = MetaFile(
            file_hash=file_hash,
            file_path=str(path),
            original_path=str(path),
            category=base_result.get("tag"),
            subcategory="NSFW" if is_nsfw else None,
            platform=_platform_from_fields(fields),
            moved_to=base_result.get("moved_to"),
            thumbnail_path=None,
            needs_review=needs_review,
            notes=_dedupe_note(base_result, base_result.get("tags")),
        )
        self.mdb.upsert_file(mf)

        # Track the physical path separately from the content-keyed file row,
        # so exact duplicates can be reported without duplicating metadata.
        current_path = Path(base_result.get("moved_to") or path)
        stat = _stat(current_path)
        self.mdb.record_location(
            file_hash,
            str(current_path),
            original_path=str(path),
            file_size=stat[0],
            modified_at=stat[1],
            phash=base_result.get("perceptual_hash"),
        )

        self.mdb.put_fields(fields)
        for e in entities:
            eid = self.mdb.upsert_entity(e)
            if eid > 0:
                self.mdb.link_file_entity(file_hash, eid, role=e.entity_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(path: Path, fast: bool = True) -> str:
    try:
        from .hasher import hash_file
        return hash_file(path, fast=fast)
    except Exception:
        return str(path)


def _stat(path: Path) -> tuple[int | None, float | None]:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return None, None


def _platform_from_fields(fields: list[MetaField]) -> str | None:
    for f in fields:
        if f.field_name == "platform" and f.field_value:
            return f.field_value
    return None


def _dedupe_note(base_result: dict[str, Any], tags: Any) -> str | None:
    parts = list(tags or [])
    if base_result.get("nsfw") or base_result.get("status") == "nsfw":
        parts.append("nsfw")
    dup = base_result.get("metadata_duplicate") or {}
    if dup.get("reason") and dup.get("duplicate_of"):
        parts.append(f"duplicate:{dup['reason']}:{str(dup['duplicate_of'])[:12]}")
    return "; ".join(parts) or None