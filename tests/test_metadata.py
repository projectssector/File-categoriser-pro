"""Tests for the metadata + spreadsheet layer (Phase 1/2 additions)."""
import pytest

from file_categorizer.core.entities import parse_candidates
from file_categorizer.core.metadata_db import (
    MetaEntity,
    MetaField,
    MetaFile,
    MetadataDatabase,
)


@pytest.fixture
def mdb(tmp_path):
    db = MetadataDatabase(tmp_path / "meta.db")
    db.init_schema()
    return db


def test_meta_file_roundtrip(mdb):
    mdb.upsert_file(MetaFile(file_hash="h1", file_path="/a.jpg", category="anime"))
    assert mdb.file_exists("h1")
    row = mdb.get_file("h1")
    assert row["category"] == "anime"
    assert len(mdb.all_files()) == 1


def test_count_rows(mdb):
    assert mdb.count_rows("meta_files") == 0
    mdb.upsert_file(MetaFile(file_hash="h1", file_path="/a.jpg"))
    assert mdb.count_rows("meta_files") == 1
    with pytest.raises(ValueError):
        mdb.count_rows("cache")


def test_meta_file_upsert_updates_not_duplicates(mdb):
    mdb.upsert_file(MetaFile(file_hash="h1", file_path="/a.jpg", category="anime"))
    mdb.upsert_file(MetaFile(file_hash="h1", file_path="/a.jpg", moved_to="/out/a.jpg"))
    assert len(mdb.all_files()) == 1
    assert mdb.get_file("h1")["moved_to"] == "/out/a.jpg"


def test_fields_roundtrip(mdb):
    mdb.put_field(MetaField(file_hash="h1", field_name="anime_name",
                            field_value="Bleach", source="image", confidence=0.9))
    fields = mdb.get_fields("h1")
    assert len(fields) == 1
    assert mdb.get_field_value("h1", "anime_name") == "Bleach"


def test_entity_and_link(mdb):
    eid = mdb.upsert_entity(MetaEntity(entity_type="account", entity_value="@chan"))
    assert eid > 0
    same = mdb.upsert_entity(MetaEntity(entity_type="account", entity_value="@chan"))
    assert same == eid, "same entity must not be duplicated"
    mdb.link_file_entity("h1", eid, role="account")
    links = mdb.get_file_entities("h1")
    assert len(links) == 1


def test_field_correction_roundtrip(mdb):
    mdb.add_field_correction("anime_name", "Bleach", wrong_value="Bleachx",
                             file_hash="h1")
    assert mdb.get_field_correction_for_hash("h1", "anime_name") == "Bleach"


def test_enrichment_cache_roundtrip(mdb):
    mdb.put_enrichment("url:https://x", "url", {"title": "X"})
    cached = mdb.get_enrichment("url:https://x")
    assert cached == {"title": "X"}


def test_parse_candidates_empty_and_malformed():
    assert parse_candidates("h", {}) == ([], [])
    assert parse_candidates("h", "not-a-dict") == ([], [])
    assert parse_candidates("h", {"anime_name": None}) == ([], [])
    assert parse_candidates("h", {"anime_name": ""}) == ([], [])


def test_parse_candidates_maps_entities():
    fields, entities = parse_candidates(
        "h",
        {
            "anime_name": {"value": "Bleach", "source": "image", "confidence": 0.8},
            "url": {"value": "https://youtu.be/abc", "source": "image"},
            "notes": {"value": "keep this", "source": "manual"},
        },
    )
    assert {f.field_name for f in fields} == {"anime_name", "url", "notes"}
    entity_types = {e.entity_type for e in entities}
    assert entity_types == {"anime", "url"}, "notes/video_title are field-only"
    anime = next(e for e in entities if e.entity_type == "anime")
    assert anime.entity_value == "Bleach"


def test_comment_text_is_field_only():
    fields, entities = parse_candidates(
        "h",
        {
            "comment_text": {"value": "song is X by Y", "source": "comment",
                             "confidence": 0.6, "correlation": "high"},
            "song_name": {"value": "X", "source": "comment"},
        },
    )
    assert {f.field_name for f in fields} == {"comment_text", "song_name"}
    assert {e.entity_type for e in entities} == {"song"}, "comment_text is field-only"
    assert fields[0].correlation == "high"


def test_parse_candidates_tolerates_bare_strings():
    fields, entities = parse_candidates("h", {"song_name": "Some Song"})
    assert fields[0].field_value == "Some Song"
    assert entities[0].entity_type == "song"


def test_export_empty_db(mdb, tmp_path):
    from file_categorizer.core.spreadsheet import export_workbook

    out = export_workbook(mdb, tmp_path / "workbook.xlsx")
    assert out.exists()


def test_nsfw_persist_marks_subcategory_and_note(mdb, tmp_path):
    from file_categorizer.core.config_loader import Config
    from file_categorizer.core.metadata_pipeline import MetadataPipeline

    pipe = object.__new__(MetadataPipeline)
    pipe.mdb = mdb
    pipe.cfg = Config(raw={})
    pipe._persist(
        "h1",
        tmp_path / "x.jpg",
        {"tag": "Girls", "nsfw": True, "status": "nsfw"},
        [],
        [],
    )
    row = mdb.get_file("h1")
    assert row["category"] == "Girls"
    assert row["subcategory"] == "NSFW"
    assert row["notes"] == "nsfw"
