"""Tests for Phase 4 dedupe + "already recorded" logic. No models used."""
import numpy as np
import pytest

from file_categorizer.core import dedupe
from file_categorizer.core.metadata_db import MetaEntity, MetaField, MetaFile, MetadataDatabase


@pytest.fixture
def mdb(tmp_path):
    db = MetadataDatabase(tmp_path / "meta.db")
    db.init_schema()
    return db


def _file(mdb, h, path="a.png", **kw):
    mdb.upsert_file(MetaFile(file_hash=h, file_path=path, **kw))


def test_exact_duplicate_is_reported(mdb):
    _file(mdb, "deadbeef")
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    res = dedupe.check_duplicate("deadbeef", image, mdb, {"perceptual": False})
    assert res.is_duplicate
    assert res.reason == "exact"
    assert res.exact_match_hash == "deadbeef"


def test_perceptual_duplicate_is_reported(mdb, monkeypatch):
    monkeypatch.setattr(dedupe, "_phash", lambda image: "ffffffffffffffff")
    _file(mdb, "other")
    mdb.put_enrichment("phash:other", "phash", {"phash": "ffffffffffffffff"})
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    res = dedupe.check_duplicate("newfile", image, mdb, {"perceptual": True,
                                                         "phash_threshold": 6})
    assert res.is_duplicate
    assert res.reason == "perceptual"
    assert res.duplicate_of == "other"


def test_non_duplicate_returns_clean_result(mdb, monkeypatch):
    monkeypatch.setattr(dedupe, "_phash", lambda image: "0f0f0f0f0f0f0f0f")
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    res = dedupe.check_duplicate("brandnew", image, mdb, {"perceptual": True})
    assert not res.is_duplicate
    assert res.duplicate_of is None


def test_select_missing_fields_filters_known_names():
    fields = [
        MetaField(file_hash="h", field_name="song_name", field_value="A"),
        MetaField(file_hash="h", field_name="artist", field_value="B"),
    ]
    missing = dedupe.select_missing_fields(fields, {"song_name"})
    assert [f.field_name for f in missing] == ["artist"]


def test_get_field_names_returns_recorded_names(mdb):
    mdb.put_fields([
        MetaField(file_hash="h", field_name="song_name", field_value="A"),
        MetaField(file_hash="h", field_name="artist", field_value="B"),
    ])
    assert mdb.get_field_names("h") == {"song_name", "artist"}
    assert mdb.get_field_names("nope") == set()


def test_already_recorded_adds_only_missing(mdb):
    mdb.put_field(MetaField(file_hash="h", field_name="song_name", field_value="Old"))
    existing = mdb.get_field_names("h")
    incoming = [
        MetaField(file_hash="h", field_name="song_name", field_value="New"),
        MetaField(file_hash="h", field_name="artist", field_value="Someone"),
    ]
    keep = dedupe.select_missing_fields(incoming, existing)
    mdb.put_fields(keep)
    # artist added, song_name untouched (still the original single row)
    assert mdb.get_field_names("h") == {"song_name", "artist"}
    assert mdb.get_field_value("h", "song_name") == "Old"


def test_entity_dedupe_links_same_entity(mdb):
    eid1 = mdb.upsert_entity(MetaEntity(entity_type="anime", entity_value="bleach"))
    eid2 = mdb.upsert_entity(MetaEntity(entity_type="anime", entity_value="bleach",
                                        display_name="Bleach"))
    assert eid1 == eid2
    mdb.link_file_entity("h1", eid1, role="anime")
    mdb.link_file_entity("h2", eid1, role="anime")
    assert dedupe.check_entity_duplicate(mdb, "anime", "bleach") == eid1
    rows = mdb.get_file_entities("h1")
    assert len(rows) == 1 and rows[0]["display_name"] == "Bleach"


def test_check_entity_duplicate_absent_returns_none(mdb):
    assert dedupe.check_entity_duplicate(mdb, "anime", "nope") is None
