# File: src/file_categorizer/core/enrichment.py
"""
enrichment.py
=============

PURPOSE
-------
Enriches parsed entities with data looked up from external services, so the
spreadsheet can show real titles/authors/descriptions instead of only what
was visible in the image.

Sources (all optional, all cached):
  url / website ......... OpenGraph + <title> fetch (no key, stdlib only)
  video (YouTube URL) ... YouTube oEmbed (no key)
  anime ................. AniList GraphQL search (no key)
  movie_tv .............. TMDB search (needs TMDB_API_KEY env var)
  account ............... account search (off by default; placeholder)

RULES (from AI_AGENT_NOTES)
---------------------------
- Enrichment is a best-effort extra: it must NEVER raise or block the
  pipeline. Any failure returns None and is logged at debug/warning.
- Results are cached in meta_enrichment_cache via MetadataDatabase, keyed by
  "<entity_type>:<value>". A cache hit is returned without any network call.
- Toggles come from cfg.raw["enrichment"] (youtube/tmdb/anilist/opengraph/
  account_search). Missing toggles default to the config defaults.
- No new third-party dependency: HTTP uses urllib from the standard library.
- To add a new source: add a _try_<name>() function and a branch in
  enrich_entity(). Update spreadsheet columns only if you add new keys.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from .metadata_db import MetaEntity, MetadataDatabase

logger = logging.getLogger(__name__)

_UA = "FileCategorizer/3.0 (+metadata enrichment)"
_TIMEOUT = 6.0

_DEFAULT_TOGGLES = {
    "youtube": True,
    "tmdb": True,
    "anilist": True,
    "opengraph": True,
    "account_search": False,
}

_OG_RE = {
    "title": re.compile(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
    "description": re.compile(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
    "site_name": re.compile(
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    ),
}
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# HTTP helpers (monkeypatchable for tests)
# ---------------------------------------------------------------------------

def _http_text(url: str, timeout: float = _TIMEOUT) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(500_000)
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("enrichment: GET %s failed: %s", url, e)
        return None


def _http_json(
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = _TIMEOUT,
) -> dict[str, Any] | None:
    try:
        data = None
        headers = {"User-Agent": _UA, "Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        logger.debug("enrichment: JSON %s failed: %s", url, e)
        return None


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()[:500] or None


# ---------------------------------------------------------------------------
# Individual sources
# ---------------------------------------------------------------------------

def _try_opengraph(url: str) -> dict[str, Any] | None:
    html = _http_text(url)
    if not html:
        return None
    out: dict[str, Any] = {}
    for key, rx in _OG_RE.items():
        m = rx.search(html)
        if m:
            out[key] = _clean(m.group(1))
    if not out.get("title"):
        m = _TITLE_RE.search(html)
        if m:
            out["title"] = _clean(m.group(1))
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname:
        out.setdefault("site_name", parsed.hostname.replace("www.", ""))
    return out or None


def _try_youtube(url: str) -> dict[str, Any] | None:
    endpoint = (
        "https://www.youtube.com/oembed?format=json&url="
        + urllib.parse.quote(url, safe="")
    )
    data = _http_json(endpoint)
    if not data:
        return None
    return {
        "video_title": _clean(data.get("title")),
        "account_name": _clean(data.get("author_name")),
        "platform": "YouTube",
    }


def _try_anilist(title: str) -> dict[str, Any] | None:
    query = (
        "query ($s: String) { Media(search: $s, type: ANIME) { "
        "title { romaji english } siteUrl } }"
    )
    data = _http_json(
        "https://graphql.anilist.co",
        payload={"query": query, "variables": {"s": title}},
    )
    if not data:
        return None
    media = (data.get("data") or {}).get("Media") or {}
    titles = media.get("title") or {}
    name = titles.get("english") or titles.get("romaji")
    if not name:
        return None
    return {"anime_name": _clean(name), "url": media.get("siteUrl")}


def _try_tmdb(title: str) -> dict[str, Any] | None:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        logger.debug("enrichment: TMDB enabled but TMDB_API_KEY is not set")
        return None
    endpoint = (
        "https://api.themoviedb.org/3/search/multi?api_key="
        + urllib.parse.quote(api_key)
        + "&query="
        + urllib.parse.quote(title)
    )
    data = _http_json(endpoint)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    name = top.get("title") or top.get("name")
    if not name:
        return None
    return {"movie_tv_name": _clean(name), "platform": "TMDB"}


def _try_account_search(account: str) -> dict[str, Any] | None:
    """Placeholder: account content classification.

    Disabled by default because it needs a search backend. Kept as a hook so
    enabling cfg.enrichment.account_search later does not require wiring.
    """
    logger.debug("enrichment: account search not implemented for %r", account)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _toggles(cfg: Any) -> dict[str, bool]:
    raw = getattr(cfg, "raw", cfg) or {}
    section = raw.get("enrichment", {}) if isinstance(raw, dict) else {}
    merged = dict(_DEFAULT_TOGGLES)
    if isinstance(section, dict):
        merged.update({k: bool(v) for k, v in section.items() if k in merged})
    return merged


def enrich_entity(
    entity_type: str,
    entity_value: str,
    cfg: Any,
    mdb: MetadataDatabase,
) -> dict[str, Any] | None:
    """Return enrichment data for a single entity, using the cache first."""
    if not entity_value:
        return None
    if entity_type not in ("url", "website", "anime", "movie_tv", "account"):
        return None
    key = f"{entity_type}:{entity_value.strip().lower()}"

    cached = mdb.get_enrichment(key)
    if cached is not None:
        return cached or None

    toggles = _toggles(cfg)
    value = entity_value.strip()
    data: dict[str, Any] | None = None

    try:
        if entity_type in ("url", "website"):
            if toggles["opengraph"]:
                data = _try_opengraph(value)
            if toggles["youtube"] and re.search(
                r"(youtube\.com|youtu\.be)", value, re.IGNORECASE
            ):
                yt = _try_youtube(value)
                if yt:
                    data = {**(data or {}), **yt}
        elif entity_type == "anime":
            if toggles["anilist"]:
                data = _try_anilist(value)
        elif entity_type == "movie_tv":
            if toggles["tmdb"]:
                data = _try_tmdb(value)
        elif entity_type == "account":
            if toggles["account_search"]:
                data = _try_account_search(value)
    except Exception as e:  # never let enrichment break the pipeline
        logger.warning("enrichment failed for %s=%r: %s", entity_type, value, e)
        data = None

    # Cache the result (even an empty dict marks "checked, nothing found").
    mdb.put_enrichment(key, entity_type, data or {})
    return data or None


def enrich_entities(
    entities: list[MetaEntity],
    cfg: Any,
    mdb: MetadataDatabase,
) -> list[MetaEntity]:
    """Enrich entity objects in place and return the ones that got new data.

    Fills only fields that are still empty, so extractor values win.
    """
    enriched: list[MetaEntity] = []
    for e in entities:
        data = enrich_entity(e.entity_type, e.entity_value, cfg, mdb)
        if not data:
            continue
        # Only entities with a matching entity_type get their own name filled.
        if e.entity_type == "anime" and data.get("anime_name"):
            e.display_name = e.display_name or data["anime_name"]
        if e.entity_type == "movie_tv" and data.get("movie_tv_name"):
            e.display_name = e.display_name or data["movie_tv_name"]
        if e.entity_type == "account" and data.get("account_name"):
            e.display_name = e.display_name or data["account_name"]
        e.platform = e.platform or data.get("platform")
        e.url = e.url or data.get("url")
        if e.entity_type == "url" and data.get("title"):
            e.bio_summary = e.bio_summary or data.get("title")
        e.content_type = e.content_type or data.get("content_type")
        enriched.append(e)
    return enriched
