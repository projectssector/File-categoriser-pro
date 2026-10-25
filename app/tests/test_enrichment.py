"""Tests for enrichment.py (Phase 3). No network is used."""
import pytest

from file_categorizer.core import enrichment
from file_categorizer.core.metadata_db import MetaEntity, MetadataDatabase


@pytest.fixture
def mdb(tmp_path):
    db = MetadataDatabase(tmp_path / "meta.db")
    db.init_schema()
    return db


def _cfg(**toggles):
    base = {"opengraph": True, "youtube": True, "anilist": True,
            "tmdb": True, "account_search": False}
    base.update(toggles)
    return {"enrichment": base}


def test_opengraph_enrichment_is_cached(mdb, monkeypatch):
    calls = []

    def fake_text(url, timeout=6.0):
        calls.append(url)
        return '<meta property="og:title" content="Cool Site">' \
               '<meta property="og:description" content="A description">' \
               '<meta property="og:site_name" content="cool.example">'

    monkeypatch.setattr(enrichment, "_http_text", fake_text)

    first = enrichment.enrich_entity("url", "https://cool.example/a", _cfg(), mdb)
    assert first["title"] == "Cool Site"
    assert first["description"] == "A description"
    assert len(calls) == 1

    second = enrichment.enrich_entity("url", "https://cool.example/a", _cfg(), mdb)
    assert second == first
    assert len(calls) == 1, "second call must come from the cache"


def test_youtube_branch_merges_video_data(mdb, monkeypatch):
    monkeypatch.setattr(enrichment, "_http_text", lambda url, timeout=6.0: "")
    monkeypatch.setattr(
        enrichment, "_try_youtube",
        lambda url: {"video_title": "My Video", "account_name": "Chan",
                     "platform": "YouTube"},
    )
    data = enrichment.enrich_entity(
        "url", "https://www.youtube.com/watch?v=abc", _cfg(), mdb
    )
    assert data["video_title"] == "My Video"
    assert data["platform"] == "YouTube"


def test_toggle_off_skips_source(mdb, monkeypatch):
    monkeypatch.setattr(
        enrichment, "_http_text",
        lambda url, timeout=6.0: '<meta property="og:title" content="X">',
    )
    data = enrichment.enrich_entity(
        "url", "https://x.example", _cfg(opengraph=False, youtube=False), mdb
    )
    assert data is None


def test_unknown_entity_type_returns_none_and_is_not_cached(mdb):
    assert enrichment.enrich_entity("platform", "YouTube", _cfg(), mdb) is None
    assert mdb.get_enrichment("platform:youtube") is None


def test_enrich_entities_fills_entity_fields(mdb, monkeypatch):
    monkeypatch.setattr(
        enrichment, "_try_anilist",
        lambda title: {"anime_name": "Bleach", "url": "https://anilist.co/1"},
    )
    ents = [MetaEntity(entity_type="anime", entity_value="bleach")]
    enriched = enrichment.enrich_entities(ents, _cfg(), mdb)
    assert len(enriched) == 1
    assert enriched[0].display_name == "Bleach"
    assert enriched[0].url == "https://anilist.co/1"


def test_enrichment_never_raises_on_network_error(mdb, monkeypatch):
    def boom(url, timeout=6.0):
        raise RuntimeError("network down")

    monkeypatch.setattr(enrichment, "_http_text", boom)
    # _http_text raising is caught inside _try_opengraph's caller loop
    assert enrichment.enrich_entity("url", "https://x.example", _cfg(), mdb) is None
