"""Orchestrates CLIP → Gemini fallback with owner bias and cache."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .config_loader import Config
from .db import Database
from .guidelines import build_prompt
from .hasher import hash_file
from .owner_hint import apply_owner_bias, get_folder_owner
from ..models.base import Prediction
from ..models.clip_model import CLIPClassifier
from ..models.gemini_model import GeminiClassifier

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.clip = CLIPClassifier(
            model_name=config.models["prefilter"]["model"],
            pretrained=config.models["prefilter"]["pretrained"],
        )
        self.gemini = GeminiClassifier(model_name=config.models["deep"]["model"])

    def classify(
        self,
        image: np.ndarray,
        path: str | Path,
        user_tags: list[str] | None = None,
    ) -> Prediction:
        categories = list(self.config.categories.keys())

        # 0. Explicit user tag that matches a category wins outright.
        if user_tags:
            for tag in user_tags:
                match = next(
                    (c for c in categories if c.lower() == tag.strip().lower()), None
                )
                if match:
                    return Prediction(tag=match, confidence=1.0, model="tag")

        file_hash = hash_file(path, fast=True)

        # 1. Cache hit?
        if (entry := self.db.get_cached(file_hash)) is not None:
            log.info("cache hit: %s -> %s", path, entry.tag)
            return Prediction(tag=entry.tag, confidence=entry.confidence, model="cache")

        # 2. Prior correction?
        if (fixed := self.db.get_correction(file_hash)) is not None:
            return Prediction(tag=fixed, confidence=1.0, model="correction")

        # 3. CLIP prefilter
        pred = self.clip.predict(image, categories)

        # 4. Owner bias
        owner = get_folder_owner(path)
        if pred.all_scores:
            biased = apply_owner_bias(pred.all_scores, owner, self.config.owner_hints)
            if biased:
                top = max(biased, key=biased.get)
                pred = Prediction(tag=top, confidence=biased[top], model="clip+owner",
                                  all_scores=biased)

        # 5. Gemini fallback if low confidence
        threshold = self.config.models["prefilter"]["confidence_threshold"]
        if pred.confidence < threshold and self.gemini.available:
            log.info("low confidence (%.2f) -> Gemini fallback", pred.confidence)
            try:
                prompt = build_prompt(self.config.categories, candidate_tags=categories)
                gem = self.gemini.predict(image, prompt, categories)
                if gem.tag != "unknown":
                    pred = gem
            except Exception as exc:
                # A Gemini outage must never lose the CLIP result.
                log.warning("Gemini fallback failed, keeping CLIP result: %s", exc)

        # 6. Store in cache
        self.db.put_cache(file_hash, str(path), pred.tag, pred.confidence, pred.model)
        return pred