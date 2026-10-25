# File: src/file_categorizer/core/image_info.py
"""
image_info.py
=============

Collects the cheap, local facts about an indexed image so the workbook is
useful without OCR or a vision model: size, dimensions, format, EXIF capture
date, camera/lens, orientation, GPS and perceptual hash.

This is the "Lap-style" indexer part of the merge: indexing means reading the
file and recording what it already says about itself, not asking the user to
type tags.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from .metadata_db import MetaField

logger = logging.getLogger(__name__)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    except (OSError, ValueError, OverflowError):
        return None


def _s(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("\x00")
    return text or None


def _field(name: str, value: Any, confidence: float = 1.0,
           evidence: str = "local metadata") -> MetaField:
    return MetaField(
        file_hash="",
        field_name=name,
        field_value=_s(value),
        source="image",
        confidence=confidence,
        evidence=evidence,
    )


def _gps_decimal(values: Any, ref: Any) -> float | None:
    try:
        parts = list(values)
        if len(parts) < 3:
            return None
        degree = float(parts[0])
        minute = float(parts[1])
        second = float(parts[2])
        decimal = degree + (minute / 60.0) + (second / 3600.0)
        if _s(ref) and str(ref).upper() in ("S", "W"):
            decimal = -decimal
        return round(decimal, 7)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gps_from_exif(exif: Any) -> tuple[float | None, float | None]:
    lat = lon = None
    try:
        from PIL import ExifTags  # type: ignore

        try:
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except Exception:
            gps = exif.get(34853) or {}
        if gps:
            lat = _gps_decimal(gps.get(2), gps.get(1))
            lon = _gps_decimal(gps.get(4), gps.get(3))
    except Exception:
        pass
    return lat, lon


def collect_image_info(
    path: str | Path,
    image_bgr: np.ndarray | None = None,
    phash: str | None = None,
    file_hash: str = "",
) -> list[MetaField]:
    """Return MetaField rows describing the file and its image metadata."""
    path = Path(path)
    fields: list[MetaField] = []

    def add(name: str, value: Any, confidence: float = 1.0,
            evidence: str = "local metadata") -> None:
        if value in (None, ""):
            return
        f = _field(name, value, confidence, evidence)
        f.file_hash = file_hash
        fields.append(f)

    try:
        stat = path.stat()
        add("file_size", stat.st_size)
        add("created_at", _iso(stat.st_ctime))
        add("modified_at", _iso(stat.st_mtime))
    except OSError as exc:
        logger.debug("image_info: stat failed for %s: %s", path, exc)

    add("image_format", path.suffix.lstrip(".").upper() or None)

    width = height = None
    if image_bgr is not None and getattr(image_bgr, "shape", None):
        try:
            height, width = int(image_bgr.shape[0]), int(image_bgr.shape[1])
        except (IndexError, TypeError, ValueError):
            width = height = None

    try:
        from PIL import ExifTags  # type: ignore
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            width, height = im.size
            add("image_format", im.format or path.suffix.lstrip(".").upper())
            add("image_mode", im.mode)
            exif = im.getexif()
            if exif:
                taken = exif.get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
                add("taken_date", _s(taken), 0.95, "EXIF capture date")
                add("camera_make", _s(exif.get(271)), 0.95, "EXIF camera make")
                add("camera_model", _s(exif.get(272)), 0.95, "EXIF camera model")
                add("lens_model", _s(exif.get(42036)), 0.9, "EXIF lens model")
                add("orientation", _s(exif.get(274)), 0.95, "EXIF orientation")
                lat, lon = _gps_from_exif(exif)
                add("gps_latitude", lat, 0.9, "EXIF GPS")
                add("gps_longitude", lon, 0.9, "EXIF GPS")
    except Exception as exc:
        logger.debug("image_info: EXIF read skipped for %s: %s", path, exc)

    add("image_width", width)
    add("image_height", height)
    add("phash", phash, 0.9, "perceptual hash")
    return fields
