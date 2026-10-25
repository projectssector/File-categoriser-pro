# File: src/file_categorizer/core/learning.py
"""
learning.py
===========

PURPOSE
-------
Field-level learning (Phase 6). Turns saved corrections into future wins:

  1. FIELD CORRECTIONS
     When the user fixes a field in the Review panel, a row is written to
     meta_field_corrections (by file hash and/or by entity). This module
     re-applies those corrections the NEXT time a matching file/entity is
     seen, so the corrected value comes back automatically (source
     "learned", confidence 1.0).

  2. ENTITY -> CATEGORY MEMORY
     The existing ``patterns`` table (owned by core/db.py) is dormant. We
     now write a pattern for every entity on a correction, and consult it
     for new files as a *suggestion*. Because entities are only known after
     classification (and the file is already moved by then), a pattern can
     never change THIS run's folder - it surfaces a suggestion and flags the
     file for review instead. This keeps the classifier cascade untouched.

RULES
-----
- Never raise into the pipeline; callers wrap us, and we also stay simple.
- Learned fields always win (confidence 1.0) but never delete anything.
- patterns are stored lowercased so "Chan" and "chan" remember together.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from .db import Database
from .metadata_db import MetaEntity, MetaField, MetadataDatabase

logger = logging.getLogger(__name__)

# Entity types worth memorising as category hints.
_MEMORY_TYPES = {"account", "url", "website", "anime", "movie_tv", "song", "artist"}

# Words ignored when turning a teaching note into learnable keyword hints.
_NOTE_STOPWORDS = {
    "the", "and", "for", "this", "that", "with", "from", "into", "image",
    "picture", "photo", "screenshot", "comment", "comments", "section",
    "look", "looks", "looked", "looks", "what", "when", "where", "why",
    "how", "are", "was", "were", "has", "have", "had", "not", "but", "you",
    "your", "his", "her", "its", "our", "their", "they", "them", "she",
    "him", "who", "which", "about", "over", "under", "left", "right",
    "top", "bottom", "here", "there", "same", "really", "very", "just",
    "like", "use", "used", "make", "made", "note", "notes", "teach",
    "teaches", "teach", "look", "logo", "text", "name", "named", "shows",
    "show", "shown", "seen", "appears", "appear", "should", "could",
    "would", "than", "then", "also", "more", "most", "some", "any", "all",
    "one", "two", "got", "get", "put", "out", "off", "own", "new", "old",
}

# Tokens keep @handles and #tags intact so they match entity values.
_TOKEN_RE = re.compile(r"[#@]?[A-Za-z0-9_]{3,}")


# ---------------------------------------------------------------------------
# Field corrections
# ---------------------------------------------------------------------------

def _entity_value(e: Any) -> str | None:
    return e.get("entity_value") if isinstance(e, dict) else getattr(e, "entity_value", None)


def _entity_type(e: Any) -> str | None:
    return e.get("entity_type") if isinstance(e, dict) else getattr(e, "entity_type", None)


def apply_field_corrections(
    file_hash: str,
    fields: list[MetaField],
    entities: Iterable[Any],
    mdb: MetadataDatabase,
) -> tuple[list[MetaField], list[MetaField]]:
    """Return (fields, learned) with stored corrections re-applied.

    Hash-level corrections are applied first, then entity-level corrections
    (entity-specific knowledge is considered more targeted, so it wins).
    """
    overrides: dict[str, tuple[str, str]] = {}
    try:
        for name, value in mdb.get_hash_field_corrections(file_hash).items():
            overrides[name] = (value, "hash")
        for e in entities:
            etype, evalue = _entity_type(e), _entity_value(e)
            if not etype or not evalue:
                continue
            for name, value in mdb.get_entity_field_corrections(etype, evalue).items():
                overrides[name] = (value, f"entity:{etype}")
    except Exception as exc:  # never break extraction
        logger.warning("field-correction lookup failed: %s", exc)
        return list(fields), []

    by_name = {f.field_name: f for f in fields}
    learned: list[MetaField] = []
    for name, (value, origin) in overrides.items():
        current = by_name.get(name)
        if current is not None and current.field_value == value:
            continue
        learned_field = MetaField(
            file_hash=file_hash,
            field_name=name,
            field_value=value,
            source="learned",
            confidence=1.0,
            evidence=f"learned from a past correction ({origin})",
        )
        by_name[name] = learned_field
        learned.append(learned_field)

    merged: list[MetaField] = []
    seen: set[str] = set()
    for f in fields:
        merged.append(by_name[f.field_name])
        seen.add(f.field_name)
    for f in learned:
        if f.field_name not in seen:
            merged.append(f)
    return merged, learned


# ---------------------------------------------------------------------------
# Entity -> category memory (patterns table)
# ---------------------------------------------------------------------------

def remember_entities_as_patterns(
    db: Database,
    entities: Iterable[Any],
    category: str,
) -> int:
    """Store entity->category patterns so future files can be hinted."""
    if not category:
        return 0
    stored = 0
    for e in entities:
        etype, evalue = _entity_type(e), _entity_value(e)
        if not etype or not evalue or etype not in _MEMORY_TYPES:
            continue
        try:
            db.upsert_pattern(str(evalue).strip().lower(), category)
            stored += 1
        except Exception as exc:
            logger.warning("could not store pattern for %r: %s", evalue, exc)
    return stored


def remember_note_keywords(
    db: Database,
    note: str,
    category: str,
    min_len: int = 3,
) -> int:
    """Turn a human teaching note into learnable keyword -> category hints.

    Every meaningful word (length >= min_len, not a stopword) in the note is
    remembered against the category the user confirmed. Those keywords then
    feed ``pattern_suggestion`` whenever they show up as an entity value on a
    later file, so a note like "naruto fan art, @artist_handle" teaches the
    sorter what to look for.
    """
    if not note or not category:
        return 0
    stored = 0
    tokens = _TOKEN_RE.findall(str(note).lower())
    for token in dict.fromkeys(tokens):
        if len(token) < min_len or token in _NOTE_STOPWORDS:
            continue
        try:
            db.upsert_pattern(token, category)
            stored += 1
        except Exception as exc:
            logger.warning("could not store note keyword %r: %s", token, exc)
    return stored


def pattern_suggestion(
    db: Database,
    entities: Iterable[Any],
    min_weight: float = 1.0,
) -> tuple[str, float] | None:
    """Return the strongest memorised (category, weight) for these entities."""
    scores: dict[str, float] = {}
    for e in entities:
        evalue = _entity_value(e)
        if not evalue:
            continue
        for category, weight in db.lookup_pattern(str(evalue).strip().lower()):
            scores[category] = scores.get(category, 0.0) + float(weight)
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return (best, scores[best]) if scores[best] >= min_weight else None
