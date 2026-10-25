from file_categorizer.core.hasher import hash_file


def test_hash_is_deterministic(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    assert hash_file(f) == hash_file(f)


def test_different_content_differs(tmp_path):
    a = tmp_path / "a.txt"; a.write_bytes(b"one")
    b = tmp_path / "b.txt"; b.write_bytes(b"two")
    assert hash_file(a) != hash_file(b)