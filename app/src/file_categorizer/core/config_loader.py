"""Loads and validates config.yaml into a typed structure."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def paths(self) -> dict[str, str]:
        return self.raw.get("paths", {})

    @property
    def categories(self) -> dict[str, dict]:
        return self.raw.get("categories", {})

    @property
    def models(self) -> dict[str, dict]:
        return self.raw.get("models", {})

    @property
    def owner_hints(self) -> dict[str, dict]:
        return self.raw.get("owner_hints", {})

    @property
    def feedback(self) -> dict[str, Any]:
        return self.raw.get("feedback", {})

    @property
    def video(self) -> dict[str, Any]:
        return self.raw.get("video", {})


def load_config(path: str | Path = "config/config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Copy config/config.example.yaml -> config/config.yaml"
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(raw=data)