"""Derive a soft category bias from the file's folder owner."""
from __future__ import annotations

import os
from pathlib import Path


def get_folder_owner(path: str | Path) -> str:
    """Return owner username. Unix: pwd lookup. Windows: best-effort fallback."""
    path = Path(path)
    try:
        st = path.stat()
        if hasattr(os, "getuid") and hasattr(__import__("pwd"), "getpwuid"):
            import pwd
            return pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, ImportError, OSError):
        pass
    return os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def apply_owner_bias(
    scores: dict[str, float],
    owner: str,
    hints: dict[str, dict],
) -> dict[str, float]:
    """Multiply tag scores by owner-specific boost factors; block listed tags."""
    hint = hints.get(owner) or hints.get("default") or {}
    boosts = hint.get("boost", {})
    blocked = set(hint.get("block", []))

    biased: dict[str, float] = {}
    for tag, score in scores.items():
        if tag in blocked:
            continue
        biased[tag] = score * boosts.get(tag, 1.0)
    return biased