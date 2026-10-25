"""Local NSFW gate. Returns True if content is unsafe."""
from __future__ import annotations

import numpy as np
from PIL import Image

try:
    from transformers import pipeline  # optional
    _HAS_TRANSFORMERS = True
except ImportError:
    _HAS_TRANSFORMERS = False


class NSFWClassifier:
    name = "nsfw"

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        if _HAS_TRANSFORMERS:
            self.pipe = pipeline(
                "image-classification",
                model="Falconsai/nsfw_image_detection",
            )
        else:
            self.pipe = None

    def is_nsfw(self, image: np.ndarray) -> tuple[bool, float]:
        if self.pipe is None:
            # Fail-open with warning; caller should log
            return False, 0.0
        pil = Image.fromarray(image[:, :, ::-1])
        results = self.pipe(pil)
        score = next((r["score"] for r in results if r["label"].lower() == "nsfw"), 0.0)
        return score >= self.threshold, score