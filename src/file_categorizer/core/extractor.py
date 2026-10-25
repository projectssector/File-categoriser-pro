# File: src/file_categorizer/core/extractor.py
"""
extractor.py
============

PURPOSE
-------
Uses a vision-language model (VLM) to extract structured metadata from an
image, optionally combined with OCR text.

Output is a dict of candidate fields ready for entities.parse_candidates().

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy into src/file_categorizer/core/.
2. In metadata_pipeline.py:
       from .extractor import Extractor
       ex = Extractor(cfg, gemini_key)
       candidates = ex.extract(image_bgr, ocr_text)
3. Pass candidates to parse_candidates().

BACKENDS
--------
- "gemini"  : uses google-generativeai (already a dependency).
- "none"    : disables extraction and returns empty dict.

NOTES FOR OTHER AI AGENTS
-------------------------
- The extractor is intentionally defensive: it asks the model for JSON,
  strips code fences, and falls back to a regex for the first {...} block.
- It never raises on model failure; returns {} and logs.
- The prompt lists the schema and tells the model to only invent fields it
  can support with visible evidence.
- Every field must include "source", "confidence", "evidence" so the review
  panel can show them.
- Do NOT expand the JSON schema without updating entities.py and the Excel
  exporter (spreadsheet.py). The three must agree on field names.
- Model choice comes from cfg.extraction["model"] (default
  "gemini-1.5-flash"). Reuse the existing Gemini API key from settings.json.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You extract structured metadata from a single image.

Rules:
- Only fill a field if you can justify it from the image or OCR text.
- If unsure, omit the field entirely. Do not guess.
- "source" must be one of: image, caption, comment, ocr, search, manual.
- "confidence" is a number from 0 to 1.
- "evidence" is a short quote or visible clue (max 160 chars).
- "correlation" is high/medium/low when the value comes from a comment and
  may or may not relate to the image. Omit otherwise.

Comment sections (IMPORTANT):
- Screenshots very often show an open comment section (a feed of comments,
  replies, usernames, likes, timestamps) below or beside the main image.
- Read that comment area carefully. Most identifying information (song,
  artist, account/handle, URL, episode, title) frequently appears in the
  comments rather than the caption.
- Put the visible comment text you rely on, verbatim where possible, into
  "comment_text", and mark the fields that come from it with
  source "comment" and a "correlation" of high/medium/low.
- Set comment_section_present to true when an open comment area is visible.

Return ONLY a JSON object. No prose. No markdown. Schema:

{
  "is_screenshot": true,
  "comment_section_present": true,
  "comment_text":    {"value": "...", "source": "comment", "confidence": 0.6,
                      "evidence": "...", "correlation": "high"},
  "platform": {"value": "YouTube", "source": "image",
               "confidence": 0.9, "evidence": "YouTube logo"},
  "main_image_description": {"value": "...", "source": "image",
                             "confidence": 0.8, "evidence": "..."},
  "anime_name":      {"value": "...", "source": "image", "confidence": 0.8, "evidence": "..."},
  "movie_tv_name":   {"value": "...", "source": "caption", "confidence": 0.7, "evidence": "..."},
  "website_name":    {"value": "...", "source": "image", "confidence": 0.6, "evidence": "..."},
  "url":             {"value": "https://...", "source": "image", "confidence": 0.9, "evidence": "..."},
  "video_title":     {"value": "...", "source": "caption", "confidence": 0.7, "evidence": "..."},
  "account_name":    {"value": "@...", "source": "image", "confidence": 0.9, "evidence": "..."},
  "display_name":    {"value": "...", "source": "image", "confidence": 0.8, "evidence": "..."},
  "song_name":       {"value": "...", "source": "comment", "confidence": 0.7,
                      "evidence": "...", "correlation": "low"},
  "artist":          {"value": "...", "source": "comment", "confidence": 0.7,
                      "evidence": "...", "correlation": "low"},
  "category":        {"value": "...", "source": "image", "confidence": 0.6, "evidence": "..."},
  "subcategory":     {"value": "...", "source": "image", "confidence": 0.5, "evidence": "..."},
  "notes":           {"value": "...", "source": "manual", "confidence": 1.0, "evidence": ""}
}

OCR text (may be empty):
---
{OCR_TEXT}
---
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_to_json(text: str) -> str:
    if not text:
        return ""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _OBJECT_RE.search(text)
    if m:
        return m.group(0).strip()
    return text.strip()


def _safe_load(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    try:
        data = json.loads(_strip_to_json(text))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Could not parse extractor JSON: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class Extractor:
    def __init__(self, cfg: dict[str, Any] | None, api_key: str | None = None):
        self.cfg = cfg or {}
        self.api_key = api_key
        self.backend = str(self.cfg.get("backend", "gemini")).lower()
        self.model_name = str(self.cfg.get("model", "gemini-2.5-flash"))
        self.max_output_tokens = int(self.cfg.get("max_output_tokens", 1024))
        self.temperature = float(self.cfg.get("temperature", 0.2))
        self._model = None
        self._available = False
        self._init_backend()

    def _init_backend(self) -> None:
        if self.backend == "none":
            logger.info("Extractor backend disabled (backend='none').")
            return
        if self.backend == "gemini":
            if not self.api_key:
                logger.warning("Extractor: no Gemini API key supplied. Disabled.")
                return
            try:
                import google.generativeai as genai  # type: ignore
                from .gemini_resolver import resolve_model_name
                genai.configure(api_key=self.api_key)
                resolved = resolve_model_name(self.model_name, self.api_key)
                self._model = genai.GenerativeModel(
                    resolved,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": self.max_output_tokens,
                    },
                )
                self._available = True
            except Exception as e:
                logger.warning("Extractor: Gemini init failed: %s", e)
        else:
            logger.warning("Extractor: unknown backend %r", self.backend)

    @property
    def available(self) -> bool:
        return self._available

    def extract(
        self,
        image_bgr: np.ndarray,
        ocr_text: str = "",
    ) -> dict[str, Any]:
        """Return a dict of candidate fields. Empty dict on failure."""
        if not self._available:
            return {}
        if image_bgr is None:
            return {}
        try:
            from PIL import Image  # type: ignore
            rgb = image_bgr[:, :, ::-1]
            pil = Image.fromarray(rgb)
        except Exception as e:
            logger.warning("Extractor: image conversion failed: %s", e)
            return {}

        prompt = SYSTEM_PROMPT.replace("{OCR_TEXT}", ocr_text or "")
        try:
            resp = self._model.generate_content([prompt, pil])
            text = getattr(resp, "text", "") or ""
        except Exception as e:
            logger.warning("Extractor: model call failed: %s", e)
            return {}

        data = _safe_load(text)
        if not data:
            return {}

        # Remove meta keys that are not fields
        for k in ("is_screenshot", "comment_section_present",
                  "main_image_description"):
            data.pop(k, None)
        return data