"""Tests for Phase 6 field-level learning. No models/network used."""
import pytest

from file_categorizer.core.db import Database
from file_categorizer.core.learning import (
    apply_field_corrections,
    pattern_suggestion,
    remember_entities_as_patterns,
    remember_note_keywords,
)
from file_categorizer.core.metadata_db import MetaEntity, MetaField, MetadataDatabase


@pytest.fixture
def mdb(tmp_path):
    db = MetadataDatabase(tmp_path / "meta.db")
    db.init_schema()
    return db


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "cache.db")


def test_hash_correction_is_reapplied(mdb):
    mdb.add_field_correction("anime_name", "Bleach", wrong_value="Bleh",
                             file_hash="h1")
    fields = [MetaField(file_hash="h1", field_name="anime_name", field_value="Bleh")]
    merged, learned = apply_field_corrections("h1", fields, [], mdb)
    assert len(learned) == 1
    assert merged[0].field_value == "Bleach"
    assert merged[0].source == "learned"


def test_entity_correction_applies_to_new_file(mdb):
    mdb.add_field_correction("anime_name", "Naruto",
                             entity_type="anime", entity_value="naruto")
    ents = [MetaEntity(entity_type="anime", entity_value="naruto")]
    # a fresh file with only an unrelated field
    merged, learned = apply_field_corrections("brand-new", [], ents, mdb)
    assert [f.field_name for f in learned] == ["anime_name"]
    assert merged[0].field_value == "Naruto"
    assert merged[0].file_hash == "brand-new"


def test_entity_beats_hash_when_both_exist(mdb):
    mdb.add_field_correction("anime_name", "FromHash", file_hash="h2")
    mdb.add_field_correction("anime_name", "FromEntity",
                             entity_type="anime", entity_value="x")
    ents = [MetaEntity(entity_type="anime", entity_value="x")]
    merged, _ = apply_field_corrections("h2", [], ents, mdb)
    assert merged[0].field_value == "FromEntity"


def test_unchanged_value_is_not_relearned(mdb):
    mdb.add_field_correction("anime_name", "Same", file_hash="h3")
    fields = [MetaField(file_hash="h3", field_name="anime_name", field_value="Same")]
    _, learned = apply_field_corrections("h3", fields, [], mdb)
    assert learned == []


def test_remember_and_suggest_patterns(db):
    ents = [
        MetaEntity(entity_type="account", entity_value="@Chan"),
        MetaEntity(entity_type="platform", entity_value="YouTube"),
    ]
    stored = remember_entities_as_patterns(db, ents, "Anime")
    assert stored == 1, "platform entities are not memorised"
    assert db.lookup_pattern("@chan") == [("Anime", pytest.approx(1.1))]

    sug = pattern_suggestion(db, [MetaEntity(entity_type="account", entity_value="@chan")])
    assert sug is not None
    assert sug[0] == "Anime"


def test_pattern_suggestion_none_when_unknown(db):
    assert pattern_suggestion(db, [MetaEntity(entity_type="account",
                                              entity_value="@nobody")]) is None


def test_note_keywords_are_learned(db):
    note = "Naruto fan art - the comment says by @artist_handle, keep this one"
    stored = remember_note_keywords(db, note, "Anime")
    assert stored > 0
    assert db.lookup_pattern("naruto") == [("Anime", pytest.approx(1.1))]
    assert db.lookup_pattern("@artist_handle") == [("Anime", pytest.approx(1.1))]
    # stopwords are not remembered
    assert db.lookup_pattern("the") == []
    assert db.lookup_pattern("this") == []


def test_note_keyword_feeds_pattern_suggestion(db):
    remember_note_keywords(db, "great bleach wallpaper", "Anime")
    sug = pattern_suggestion(
        db, [MetaEntity(entity_type="anime", entity_value="bleach")]
    )
    assert sug is not None
    assert sug[0] == "Anime"


def test_note_keywords_need_a_category(db):
    assert remember_note_keywords(db, "naruto art", "") == 0
    assert remember_note_keywords(db, "", "Anime") == 0
