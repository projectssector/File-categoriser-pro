"""Pick a Gemini model name the current API key can actually use.

Hard-coded defaults such as ``gemini-1.5-flash`` can be retired by Google and
then every call returns HTTP 404 ("model ... is not found for API version
v1beta").  Instead of trusting the configured name blindly we ask the API which
models the key can use and choose the best available one, falling back
gracefully so a missing/renamed model never breaks a run.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Preference order when the configured model is not available.
_PREFERRED = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
    "gemini-pro",
)

_FALLBACK = "gemini-2.5-flash"

_cached: dict[str, str] = {}


def resolve_model_name(preferred: str = "", api_key: str | None = None) -> str:
    """Return the name of a usable model (without the ``models/`` prefix).

    Discovery is cached per API key so it runs at most once per session.
    """
    key = (api_key or "").strip()
    if key and key in _cached:
        return _cached[key]

    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        return preferred or _FALLBACK

    try:
        if key:
            genai.configure(api_key=key)
        available: list[str] = []
        for model in genai.list_models():
            methods = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                available.append(str(getattr(model, "name", "")).replace("models/", ""))
    except Exception as exc:  # network / auth / SDK issues -> keep the preference
        log.warning("Gemini model discovery failed: %s", exc)
        return preferred or _FALLBACK

    if not available:
        return preferred or _FALLBACK

    # 1. Honour the configured model when it actually exists.
    if preferred and preferred in available:
        chosen = preferred
    else:
        # 2. Otherwise walk the preference list.
        chosen = next((p for p in _PREFERRED if p in available), None)
        # 3. Finally, any flash model, else anything.
        if chosen is None:
            flash = [a for a in available if "flash" in a.lower()]
            chosen = (flash or sorted(available))[0]

    log.info("Gemini model resolved to %r (configured %r)", chosen, preferred or None)
    if key:
        _cached[key] = chosen
    return chosen
