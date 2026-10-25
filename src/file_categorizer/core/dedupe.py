# File: src/file_categorizer/core/dedupe.py
"""
dedupe.py
=========

PURPOSE
-------
Provides three layers of dedupe:
  1. Exact file hash (SHA-256, fast mode)     -> from core/hasher.py
  2. Perceptual hash (imagehash)              -> optional dependency
  3. Entity-level dedupe                      -> uses MetadataDatabase

The goal: a different batch of images must know if the info has already
been recorded, and skip or update instead of duplicating.

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy into src/file_categorizer/core/.
2. In metadata_pipeline.py:
       from .dedupe import DedupeResult, check_duplicate
       result = check_duplicate(file_hash, image_bgr, mdb)
       if result.duplicate_of:
           # update missing fields, do not re-insert
3. Perceptual hash requires "imagehash" + "Pillow". If missing, that
   layer is skipped silently.

INSTALL (optional)
------------------
    pip install imagehash Pillow

NOTES FOR OTHER AI AGENTS
-------------------------
- check_duplicate() returns a DedupeResult with:
    * exact_match_hash: str | None
    * perceptual_match_hash: str | None
    * duplicate_of: str | None   (best guess of the original file_hash)
    * reason: str | None         ("exact" | "perceptual" | "entity")
- It never deletes files. It only reports duplicates.
- Entity-level dedupe is checked by the caller after extraction, because
  it needs parsed entity values, not just the image.
- Perceptual hash threshold default is 6 (Hamming distance). Adjustable
  in cfg.dedupe["phash_threshold"].
- Persisting perceptual hashes is done via MetadataDatabase.put_enrichment
  keyed as "phash:<hash>" so we do not add yet another table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from .metadata_db import MetadataDatabase

logger = logging.getLogger(__name__)


@dataclass
class DedupeResult:
    exact_match_hash: str | None = None
    perceptual_match_hash: str | None = None
    duplicate_of: str | None = None
    reason: str | None = None
    phash: str | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of is not None


# ---------------------------------------------------------------------------
# Perceptual hash helpers
# ---------------------------------------------------------------------------

def perceptual_hash(image_bgr: np.ndarray) -> str | None:
    """Return an imagehash pHash for an OpenCV BGR image (or None)."""
    try:
        import imagehash  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        rgb = image_bgr[:, :, ::-1]
        pil = Image.fromarray(rgb)
        return str(imagehash.phash(pil))
    except Exception as e:
        logger.warning("phash failed: %s", e)
        return None


def _phash(image_bgr: np.ndarray) -> str | None:
    """Backwards-compatible private alias (tests monkeypatch this name)."""
    return perceptual_hash(image_bgr)


def _hamming(a: str, b: str) -> int:
    """Hamming distance between two hex phash strings."""
    try:
        ia = int(a, 16)
        ib = int(b, 16)
    except Exception:
        return 999
    return bin(ia ^ ib).count("1")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_duplicate(
    file_hash: str,
    image_bgr: np.ndarray,
    mdb: MetadataDatabase,
    cfg: dict[str, Any] | None = None,
    phash: str | None = None,
) -> DedupeResult:
    cfg = cfg or {}
    result = DedupeResult(phash=phash)

    # Layer 1 - exact hash
    if mdb.file_exists(file_hash):
        result.exact_match_hash = file_hash
        result.duplicate_of = file_hash
        result.reason = "exact"
        return result

    # Layer 2 - perceptual hash (optional)
    if cfg.get("perceptual", True):
        if phash is None:
            phash = _phash(image_bgr)
        result.phash = phash
        if phash:
            threshold = int(cfg.get("phash_threshold", 6))
            candidates = mdb.all_files()
            for row in candidates:
                other = mdb.get_field_value(row["file_hash"], "phash")
                if not other:
                    stored = mdb.get_enrichment(f"phash:{row['file_hash']}")
                    other = stored.get("phash") if stored else None
                if not other:
                    continue
                if _hamming(phash, other) <= threshold:
                    result.perceptual_match_hash = row["file_hash"]
                    result.duplicate_of = row["file_hash"]
                    result.reason = "perceptual"
                    return result
            # Save this phash for future comparisons
            mdb.put_enrichment(f"phash:{file_hash}", "phash", {"phash": phash})

    return result


def check_entity_duplicate(
    mdb: MetadataDatabase,
    entity_type: str,
    entity_value: str,
) -> int | None:
    """
    Returns the entity_id if this entity already exists, else None.
    Used after extraction to detect "already recorded" entities.
    """
    row = mdb.get_entity(entity_type, entity_value)
    if row:
        return int(row["id"])
    return None


def select_missing_fields(
    fields: list[Any],
    existing_names: set[str],
) -> list[Any]:
    """Return only the fields whose field_name is not already recorded.

    Used for the "already recorded" rule: a re-processed file only gains
    fields it did not have, so we never pile up duplicate rows.
    """
    return [f for f in fields if f.field_name not in existing_names]