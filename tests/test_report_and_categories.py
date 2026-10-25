from file_categorizer.core.categories import CategoryStore
from file_categorizer.core.report import Report


def test_category_store_roundtrip(tmp_path):
    store = CategoryStore(tmp_path / "cats.json")
    store.add("gaming", ["HUD overlays", "score counters"])
    assert store.has("gaming")

    reloaded = CategoryStore(tmp_path / "cats.json")
    assert reloaded.all()["gaming"]["scan_for"] == ["HUD overlays", "score counters"]

    reloaded.remove("gaming")
    assert not CategoryStore(tmp_path / "cats.json").has("gaming")


def test_category_store_rejects_empty(tmp_path):
    store = CategoryStore(tmp_path / "cats.json")
    try:
        store.add("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty category name should raise")


def test_report_has_classification_and_anime_tables():
    report = Report()
    report.add("/inbox/naruto_01.jpg", "anime", 0.9, "clip", ["naruto"])
    report.add("/inbox/beach.jpg", "photo", 0.8, "clip", [])
    text = report.build()
    assert "CLASSIFICATION TABLE" in text
    assert "ANIME TABLE" in text
    assert "naruto" in text
    assert "naruto_01.jpg" in text


def test_report_saves_to_disk(tmp_path):
    report = Report()
    report.add("/inbox/a.jpg", "photo", 0.5, "clip", [])
    path = report.save(tmp_path)
    assert path.exists()
    assert "CLASSIFICATION TABLE" in path.read_text(encoding="utf-8")
