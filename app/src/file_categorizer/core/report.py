"""Builds and saves text reports (ASCII tables) of classification results."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _table(headers: list[str], rows: list[list[str]]) -> str:
    cells = [headers] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def render(row: list[str]) -> str:
        return "| " + " | ".join(
            str(cell).ljust(widths[i]) for i, cell in enumerate(row)
        ) + " |"

    lines = [sep, render(headers), sep]
    lines.extend(render(row) for row in rows)
    lines.append(sep)
    return "\n".join(lines)


class Report:
    """Accumulates results and renders tables for the text editor / log file."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(
        self,
        image: str,
        category: str,
        confidence: float,
        model: str,
        tags: list[str] | None = None,
    ) -> None:
        self.rows.append(
            {
                "image": image,
                "category": category or "unknown",
                "confidence": float(confidence or 0.0),
                "model": model or "",
                "tags": list(tags or []),
            }
        )

    @staticmethod
    def name_for(row: dict) -> str:
        if row["tags"]:
            return row["tags"][0]
        return Path(row["image"]).stem

    def build(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        out = [
            "FILE CATEGORIZER REPORT",
            f"Generated: {now}",
            "=" * 60,
            "",
            "CLASSIFICATION TABLE",
            _table(
                ["Image", "Category", "Confidence", "Model", "Tags"],
                [
                    [
                        Path(r["image"]).name,
                        r["category"],
                        f"{r['confidence']:.0%}",
                        r["model"],
                        ", ".join(r["tags"]),
                    ]
                    for r in self.rows
                ]
                or [["-", "-", "-", "-", "-"]],
            ),
            "",
        ]

        categories = sorted({r["category"] for r in self.rows})
        for category in categories:
            subset = [r for r in self.rows if r["category"] == category]
            out.append(f"CATEGORY TABLE: {category.upper()}")
            out.append(
                _table(
                    ["Image", "Name", "Confidence", "Model"],
                    [
                        [
                            Path(r["image"]).name,
                            self.name_for(r),
                            f"{r['confidence']:.0%}",
                            r["model"],
                        ]
                        for r in subset
                    ],
                )
            )
            out.append("")

        anime = [
            r
            for r in self.rows
            if r["category"].lower() == "anime" or r["tags"]
        ]
        if anime:
            out.append("ANIME TABLE")
            out.append(
                _table(
                    ["Anime Name", "Image"],
                    [[self.name_for(r), Path(r["image"]).name] for r in anime],
                )
            )
            out.append("")

        return "\n".join(out)

    def save(self, directory: str | Path = "data/reports") -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"report_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path.write_text(self.build(), encoding="utf-8")
        return path
