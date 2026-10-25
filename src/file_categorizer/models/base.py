"""Common interface for all classifier backends."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Prediction:
    tag: str
    confidence: float
    model: str
    all_scores: dict[str, float] | None = None


class Classifier(Protocol):
    name: str

    def predict(self, image: np.ndarray, categories: list[str]) -> Prediction: ...