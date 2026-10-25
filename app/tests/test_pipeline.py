from unittest.mock import MagicMock
from file_categorizer.core.db import Database
from file_categorizer.core.config_loader import Config


def test_pipeline_constructs(tmp_path):
    cfg = Config(raw={
        "paths": {"inbox": str(tmp_path), "nsfw": str(tmp_path / "NSFW"),
                  "database": str(tmp_path / "db.sqlite")},
        "categories": {"anime": {"scan_for": ["linework"]}},
        "models": {
            "prefilter": {"type": "clip", "model": "ViT-B-32",
                          "pretrained": "laion2b_s34b_b79k",
                          "confidence_threshold": 0.75},
            "deep": {"type": "gemini", "model": "gemini-1.5-flash"},
            "nsfw": {"type": "clip_nsfw", "threshold": 0.85},
        },
        "owner_hints": {},
        "feedback": {"confidence_threshold": 0.75},
        "video": {"frame_positions": [0.1, 0.5, 0.9]},
    })
    db = Database(cfg.paths["database"])
    # Just ensure construction path works; heavy models are lazily built.
    assert db is not None


def test_safe_category_name():
    from file_categorizer.core.pipeline import safe_category_name

    assert safe_category_name("Anime") == "Anime"
    assert safe_category_name("a/b\\c:d") == "a_b_c_d"
    assert safe_category_name("  ...  ") == "unsorted"
    assert safe_category_name("") == "unsorted"


def _bare_pipeline(tmp_path, monkeypatch, classify_result, cfg_extra=None):
    """Build a FilePipeline without loading the real CLIP/NSFW models."""
    import numpy as np
    from file_categorizer.core import pipeline as P

    fp = object.__new__(P.FilePipeline)
    fp.config = Config(raw={
        "paths": {"output": str(tmp_path / "out"), "nsfw": "./NSFW"},
        "models": {"nsfw": {"threshold": 0.85, **(cfg_extra or {})}},
    })
    fp.output_root = tmp_path / "out"
    fp.nsfw = MagicMock()
    fp.nsfw.is_nsfw.return_value = (True, 0.99)
    fp.classifier = MagicMock()
    fp.classifier.classify.return_value = classify_result
    monkeypatch.setattr(P, "load_image", lambda p: np.zeros((4, 4, 3), dtype="uint8"))
    return fp


def test_nsfw_file_is_also_classified_into_subfolder(tmp_path, monkeypatch):
    from file_categorizer.models.base import Prediction

    img = tmp_path / "explicit.jpg"
    img.write_bytes(b"fake")
    pred = Prediction(tag="Girls", confidence=0.9, model="clip")
    fp = _bare_pipeline(tmp_path, monkeypatch, pred)
    result = fp.process(img, dry_run=False)

    assert result["status"] == "nsfw"
    assert result["nsfw"] is True
    assert result["tag"] == "Girls"
    assert (tmp_path / "out" / "NSFW" / "Girls" / "explicit.jpg").exists()


def test_nsfw_flat_when_classify_disabled(tmp_path, monkeypatch):
    img = tmp_path / "explicit.jpg"
    img.write_bytes(b"fake")
    fp = _bare_pipeline(tmp_path, monkeypatch, None, {"classify": False})
    result = fp.process(img, dry_run=False)

    assert result["status"] == "nsfw"
    assert result["tag"] == "NSFW"
    assert fp.classifier.classify.call_count == 0
    assert (tmp_path / "out" / "NSFW" / "explicit.jpg").exists()