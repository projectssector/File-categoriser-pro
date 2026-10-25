import pytest
from file_categorizer.core.config_loader import load_config


def test_load_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_load_minimal(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("paths: {inbox: /tmp}\ncategories: {anime: {scan_for: [x]}}")
    cfg = load_config(p)
    assert "inbox" in cfg.paths
    assert "anime" in cfg.categories