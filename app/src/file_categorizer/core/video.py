"""Turn a video into a 3-frame composite or GIF for classification."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def extract_frames(
    video_path: str | Path,
    positions: tuple[float, ...] = (0.1, 0.5, 0.9),
) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames: list[np.ndarray] = []
    for pos in positions:
        idx = int(total * pos)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def build_composite(frames: list[np.ndarray], target_h: int = 512) -> np.ndarray:
    """Stack frames horizontally after resizing to a common height."""
    if not frames:
        raise ValueError("No frames to composite")

    resized = []
    for f in frames:
        h, w = f.shape[:2]
        scale = target_h / h
        resized.append(cv2.resize(f, (int(w * scale), target_h)))

    return np.hstack(resized)


def video_to_composite(
    video_path: str | Path,
    positions: tuple[float, ...] = (0.1, 0.5, 0.9),
) -> np.ndarray:
    return build_composite(extract_frames(video_path, positions))