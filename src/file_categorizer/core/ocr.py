# File: src/file_categorizer/core/ocr.py
"""
ocr.py
======

PURPOSE
-------
Extracts visible text from images (screenshots, captions, comment sections,
UI, usernames, URLs). Feeds the VLM extractor and the entity parser.

It is a thin wrapper with a single run_ocr(image) function. Backends are
pluggable. Default backend is Tesseract via pytesseract (local, free).

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy into src/file_categorizer/core/.
2. In metadata_pipeline.py:
       from .ocr import run_ocr
       text = run_ocr(image_bgr)
3. Store the raw text as a field:
       MetaField(file_hash=..., field_name="extracted_text",
                 field_value=text, source="ocr")

INSTALL
-------
- Local backend:   pip install pytesseract
                   + install Tesseract binary (system package)
- Optional:       pip install paddleocr  (better for screenshots/multilingual)

NOTES FOR OTHER AI AGENTS
-------------------------
- run_ocr accepts a BGR numpy array (OpenCV order), same as the rest of the
  pipeline (core/pipeline.load_image returns BGR).
- It never raises if the OCR engine is missing: it logs and returns "".
- Set cfg.ocr["enabled"] = False to skip OCR entirely for speed.
- The raw text is stored verbatim; cleaning happens in extractor.py.
- This module is intentionally dependency-light so the app still runs when
  Tesseract is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------

def _try_tesseract(image: np.ndarray, lang: str) -> str:
    try:
        import pytesseract  # type: ignore
    except Exception as e:
        logger.warning("pytesseract not installed: %s", e)
        return ""
    try:
        return pytesseract.image_to_string(image, lang=lang) or ""
    except Exception as e:
        logger.warning("Tesseract OCR failed: %s", e)
        return ""


def _try_paddle(image: np.ndarray) -> str:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as e:
        logger.warning("paddleocr not installed: %s", e)
        return ""
    try:
        # Lazy singleton
        global _PADDLE
        try:
            _PADDLE  # type: ignore
        except NameError:
            _PADDLE = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)  # type: ignore
        result = _PADDLE.ocr(image, cls=True)  # type: ignore
        lines: list[str] = []
        if result:
            for block in result:
                for line in block or []:
                    try:
                        lines.append(line[1][0])
                    except Exception:
                        continue
        return "\n".join(lines)
    except Exception as e:
        logger.warning("PaddleOCR failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ocr(
    image: np.ndarray,
    cfg: dict[str, Any] | None = None,
) -> str:
    """
    Run OCR on a BGR image.

    cfg keys (all optional):
        enabled:   bool (default True)
        backend:   "tesseract" | "paddle" (default "tesseract")
        lang:      str (default "eng")
    """
    cfg = cfg or {}
    if not cfg.get("enabled", True):
        return ""

    backend = str(cfg.get("backend", "tesseract")).lower()
    lang = str(cfg.get("lang", "eng"))

    if backend == "paddle":
        text = _try_paddle(image)
        if text.strip():
            return text
        # fall through to tesseract
    return _try_tesseract(image, lang)


def is_available(cfg: dict[str, Any] | None = None) -> bool:
    """Return True if the configured OCR backend is importable."""
    cfg = cfg or {}
    backend = str(cfg.get("backend", "tesseract")).lower()
    if backend == "paddle":
        try:
            import paddleocr  # noqa: F401
            return True
        except Exception:
            return False
    try:
        import pytesseract  # noqa: F401
        return True
    except Exception:
        return False