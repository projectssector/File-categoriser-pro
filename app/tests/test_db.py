def test_cache_roundtrip(db):
    db.put_cache("h1", "/x.jpg", "anime", 0.9, "clip")
    entry = db.get_cached("h1")
    assert entry.tag == "anime"


def test_correction_roundtrip(db):
    db.add_correction("h2", "anime", "manga")
    assert db.get_correction("h2") == "manga"


def test_pattern_weight_grows(db):
    db.upsert_pattern("*.jpg", "photo", 0.1)
    db.upsert_pattern("*.jpg", "photo", 0.1)
    (category, weight), = db.lookup_pattern("*.jpg")
    assert category == "photo"
    assert weight > 1.0