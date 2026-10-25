# File: src/file_categorizer/core/entities.py
"""
entities.py
===========

PURPOSE
-------
Turns a raw dict of candidate fields (from the VLM extractor) into a
normalized list of MetaField and MetaEntity objects that can be written
to MetadataDatabase.

This module is pure logic: no API calls, no DB writes, no images.
It only normalizes and classifies strings.

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy into src/file_categorizer/core/.
2. In metadata_pipeline.py:
       from .entities import parse_candidates
       fields, entities = parse_candidates(file_hash, candidates)
3. Write them with:
       mdb.put_fields(fields)
       for e in entities:
           eid = mdb.upsert_entity(e)
           mdb.link_file_entity(file_hash, eid, role=e.entity_type)

NOTES FOR OTHER AI AGENTS
-------------------------
- "candidates" is a plain dict, e.g.
    {
      "anime_name": {"value": "...", "source": "image",
                     "confidence": 0.82, "evidence": "..."},
      ...
    }
  or a bare string value (treated as source=manual, confidence=None).
- Known field names:
    anime_name, movie_tv_name, website_name, url, video_title,
    account_name, display_name, song_name, artist, platform,
    category, subcategory, notes, extracted_text
- Known entity types (derived from field name):
    anime_name        -> "anime"
    movie_tv_name     -> "movie_tv"
    website_name      -> "website"
    url               -> "url"
    account_name      -> "account"
    display_name      -> "account"   (with role="display_name")
    song_name         -> "song"
    artist            -> "artist"
    platform          -> "platform"
- Correlation defaults to None unless provided.
- The function never raises on unexpected input; it skips bad entries.
"""

from __future__ import annotations

import logging
from typing import Any

from .metadata_db import MetaEntity, MetaField

logger = logging.getLogger(__name__)


FIELD_TO_ENTITY = {
    "anime_name": "anime",
    "movie_tv_name": "movie_tv",
    "website_name": "website",
    "url": "url",
    "account_name": "account",
    "display_name": "account",
    "song_name": "song",
    "artist": "artist",
    "platform": "platform",
}


# Fields that are stored as extracted_fields but NOT as entities
FIELD_ONLY = {
    "video_title",
    "category",
    "subcategory",
    "notes",
    "extracted_text",
    "comment_text",
}


def _coerce(entry: Any) -> dict[str, Any]:
    """Normalize a candidate entry to a dict."""
    if entry is None:
        return {}
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, (list, tuple)) and entry:
        return {"value": entry[0]}
    return {"value": str(entry)}


def parse_candidates(
    file_hash: str,
    candidates: dict[str, Any],
) -> tuple[list[MetaField], list[MetaEntity]]:
    """
    Convert raw candidates into MetaField and MetaEntity objects.

    Returns (fields, entities).
    """
    fields: list[MetaField] = []
    entities: list[MetaEntity] = []

    if not isinstance(candidates, dict):
        logger.warning("parse_candidates got non-dict input: %r", type(candidates))
        return fields, entities

    for field_name, raw in candidates.items():
        data = _coerce(raw)
        value = data.get("value")
        if value is None:
            continue
        value = str(value).strip()
        if not value:
            continue

        field = MetaField(
            file_hash=file_hash,
            field_name=field_name,
            field_value=value,
            source=data.get("source"),
            confidence=data.get("confidence"),
            evidence=data.get("evidence"),
            correlation=data.get("correlation"),
            model_used=data.get("model_used"),
        )
        fields.append(field)

        entity_type = FIELD_TO_ENTITY.get(field_name)
        if entity_type and field_name not in FIELD_ONLY:
            entity = MetaEntity(
                entity_type=entity_type,
                entity_value=value,
                display_name=data.get("display_name"),
                platform=data.get("platform"),
                url=data.get("url"),
                bio_summary=data.get("bio_summary"),
                content_type=data.get("content_type"),
                confidence=data.get("confidence"),
            )
            entities.append(entity)

    return fields, entities


def extract_platform_from_url(url: str) -> str | None:
    """Best-effort platform guess from a URL."""
    if not url:
        return None
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u:
        return "Instagram"
    if "twitter.com" in u or "x.com" in u:
        return "X"
    if "reddit.com" in u:
        return "Reddit"
    if "pinterest." in u:
        return "Pinterest"
    if "facebook.com" in u:
        return "Facebook"
    if "twitch.tv" in u:
        return "Twitch"
    if "discord." in u:
        return "Discord"
    if "tumblr.com" in u:
        return "Tumblr"
    return None