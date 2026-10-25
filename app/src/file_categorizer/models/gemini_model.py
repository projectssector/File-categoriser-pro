"""Gemini fallback classifier for low-confidence cases."""
from __future__ import annotations

import io
import logging
import os

import numpy as np
from PIL import Image

try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False

from .base import Prediction
from ..core.gemini_resolver import resolve_model_name

log = logging.getLogger(__name__)


class GeminiClassifier:
    name = "gemini"

    def __init__(self, model_name: str = "gemini-2.5-flash", api_key: str | None = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not _HAS_GEMINI or not api_key:
            self.model = None
            return
        genai.configure(api_key=api_key)
        # Choose a model the key can actually use (configured name is preferred,
        # otherwise the next best available model).  Avoids the 404 that a
        # retired name like "gemini-1.5-flash" produces.
        resolved = resolve_model_name(model_name, api_key)
        try:
            self.model = genai.GenerativeModel(resolved)
        except Exception as exc:
            log.warning("Gemini init failed for %r: %s", resolved, exc)
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, image: np.ndarray, prompt: str, categories: list[str]) -> Prediction:
        if not self.available:
            return Prediction(tag="unknown", confidence=0.0, model=self.name)

        try:
            pil = Image.fromarray(image[:, :, ::-1])
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            buf.seek(0)

            response = self.model.generate_content(
                [prompt, {"mime_type": "image/png", "data": buf.read()}]
            )
            text = (response.text or "").strip().lower()
        except Exception as exc:
            # Never let a transient API/model error abort classification; the
            # caller keeps the CLIP result when we return "unknown".
            log.warning("Gemini predict failed: %s", exc)
            return Prediction(tag="unknown", confidence=0.0, model=self.name)

        tag = next((c for c in categories if c in text), "unknown")
        return Prediction(tag=tag, confidence=0.6, model=self.name)