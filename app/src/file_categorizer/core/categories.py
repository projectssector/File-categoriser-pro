"""Persistent user-defined categories, stored as JSON next to the runtime data."""
from __future__ import annotations

import json
from pathlib import Path

_REMOVED_KEY = "_removed"


class CategoryStore:
    """The single source of truth for the categories the user created.

    Only categories added here are used by the GUI. The sample categories that
    ship inside ``config.yaml`` are ignored so you always see exactly the list
    you built yourself. Names are matched case-insensitively, so adding
    "Anime" when "anime" already exists updates the existing entry instead of
    creating a duplicate.
    """

    def __init__(self, path: str | Path = "data/categories.json"):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        self.removed: list[str] = []
        self.load()

    def _key(self, name: str) -> str | None:
        """Return the stored name that matches ``name`` (case-insensitive)."""
        wanted = name.strip().casefold()
        for existing in self._data:
            if existing.casefold() == wanted:
                return existing
        return None

    def load(self) -> None:
        self._data = {}
        self.removed = []
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return

        for name, spec in raw.items():
            if name == _REMOVED_KEY or not isinstance(spec, dict):
                continue
            name = str(name).strip()
            if not name:
                continue
            existing = self._key(name)
            if existing is None:
                self._data[name] = spec
            else:
                # Same category with different casing -> keep a single entry.
                self._data[existing] = spec

        hidden = raw.get(_REMOVED_KEY)
        if isinstance(hidden, list):
            seen: set[str] = set()
            for entry in hidden:
                entry = str(entry).strip()
                key = entry.casefold()
                if entry and key not in seen:
                    seen.add(key)
                    self.removed.append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._data)
        if self.removed:
            payload[_REMOVED_KEY] = self.removed
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def all(self) -> dict[str, dict]:
        return {name: dict(spec) for name, spec in self._data.items()}

    def names(self) -> list[str]:
        return list(self._data)

    def add(self, name: str, cues: list[str] | None = None) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        existing = self._key(name)
        key = existing if existing is not None else name
        self._data[key] = {
            "scan_for": [c.strip() for c in (cues or []) if c.strip()]
        }
        self.removed = [n for n in self.removed if n.casefold() != name.casefold()]
        self.save()
        return key

    def remove(self, name: str) -> None:
        existing = self._key(name)
        if existing is None:
            return
        self._data.pop(existing, None)
        if not any(n.casefold() == existing.casefold() for n in self.removed):
            self.removed.append(existing)
        self.save()

    def has(self, name: str) -> bool:
        return self._key(name) is not None

    def is_removed(self, name: str) -> bool:
        return any(n.casefold() == name.strip().casefold() for n in self.removed)

    def removed_list(self) -> list[str]:
        return list(self.removed)
