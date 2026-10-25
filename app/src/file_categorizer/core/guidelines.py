"""Builds model prompts from per-category scanning rules."""
from __future__ import annotations


def build_prompt(
    categories: dict[str, dict],
    candidate_tags: list[str] | None = None,
) -> str:
    """Inject only the scan rules for categories in contention."""
    lines = [
        "Classify the image into exactly one of the following categories.",
        "Use the listed visual cues when deciding.",
        "",
    ]
    for name, spec in categories.items():
        if candidate_tags is not None and name not in candidate_tags:
            continue
        lines.append(f"Category: {name}")
        for cue in spec.get("scan_for", []):
            lines.append(f"  - {cue}")
        lines.append("")

    lines.append("Respond with the category name and a confidence 0-1.")
    return "\n".join(lines)