"""End-to-end: file → NSFW gate → classifier → move."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import cv2
import numpy as np

from .classifier import Pipeline as ClassifierPipeline
from .config_loader import Config
from .db import Database
from .video import video_to_composite
from ..models.nsfw_model import NSFWClassifier

log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_category_name(tag: str) -> str:
    """Sanitise a category/tag so it is always a single, valid folder name."""
    name = _UNSAFE_NAME_RE.sub("_", str(tag or "")).strip().strip(".")
    return name or "unsorted"


def load_image(path: Path) -> np.ndarray | None:
    if path.suffix.lower() in IMAGE_EXTS:
        return cv2.imread(str(path))
    if path.suffix.lower() in VIDEO_EXTS:
        return video_to_composite(path)
    return None


def unique_destination(target: Path) -> Path:
    """Never overwrite an existing file that happens to share a name."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 2
    while True:
        candidate = target.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


class FilePipeline:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.classifier = ClassifierPipeline(config, db)
        self.nsfw = NSFWClassifier(threshold=config.models["nsfw"]["threshold"])
        self.output_root = Path(config.paths.get("output", "output"))

    def process(
        self,
        path: Path,
        dry_run: bool = False,
        user_tags: list[str] | None = None,
    ) -> dict:
        path = Path(path)
        if not path.exists():
            # The file was moved/renamed (e.g. a queue restored from a session
            # where it was already sorted) or deleted.  Report it distinctly so
            # it is not confused with an unreadable image.
            return {"path": str(path), "status": "missing",
                    "error": "file not found (already moved or deleted)"}
        image = load_image(path)
        if image is None:
            return {"path": str(path), "status": "unsupported",
                    "error": "could not decode file as image/video"}

        # NSFW gate first
        is_nsfw, score = self.nsfw.is_nsfw(image)
        if is_nsfw:
            return self._handle_nsfw(path, image, score, dry_run, user_tags)

        # Classify
        pred = self.classifier.classify(image, path, user_tags=user_tags)
        target_dir = self.output_root / safe_category_name(pred.tag)
        target = unique_destination(target_dir / path.name)
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if path.resolve() != target.resolve():
                shutil.move(str(path), target)

        return {
            "path": str(path),
            "status": "classified",
            "tag": pred.tag,
            "confidence": pred.confidence,
            "model": pred.model,
            "tags": list(user_tags or []),
            "moved_to": str(target),
        }

    def _handle_nsfw(
        self,
        path: Path,
        image: np.ndarray,
        score: float,
        dry_run: bool,
        user_tags: list[str] | None,
    ) -> dict:
        """Quarantine an explicit file, yet keep the normal sorting benefits.

        Explicit files are still content-classified (anime / photo / girls /
        whatever categories you defined) and filed under ``NSFW/<category>/``
        so they stay separated but remain sorted, reportable and exportable.
        Set ``models.nsfw.classify: false`` to keep the old flat behaviour, or
        ``models.nsfw.subfolder: false`` to classify without the per-category
        sub-folder.
        """
        cfg = self.config.models.get("nsfw", {})
        nsfw_name = Path(self.config.paths.get("nsfw", "NSFW")).name or "NSFW"
        root = self.output_root / nsfw_name
        classify = bool(cfg.get("classify", True))
        subfolder = bool(cfg.get("subfolder", True))

        pred = self.classifier.classify(image, path, user_tags=user_tags) \
            if classify else None

        target_dir = root
        if pred is not None and subfolder:
            target_dir = root / safe_category_name(pred.tag)
        target = unique_destination(target_dir / path.name)
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if path.resolve() != target.resolve():
                shutil.move(str(path), target)

        result = {
            "path": str(path),
            "status": "nsfw",
            "score": score,
            "nsfw": True,
            "moved_to": str(target),
        }
        if pred is not None:
            result.update({
                "tag": pred.tag,
                "confidence": pred.confidence,
                "model": pred.model,
                "tags": list(user_tags or []),
            })
        else:
            result["tag"] = "NSFW"
            result["model"] = "nsfw"
        return result