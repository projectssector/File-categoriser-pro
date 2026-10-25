"""SQLite cache, corrections, and pattern memory."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    file_hash     TEXT PRIMARY KEY,
    path          TEXT NOT NULL,
    tag           TEXT NOT NULL,
    confidence    REAL,
    model         TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash     TEXT NOT NULL,
    wrong_tag     TEXT,
    right_tag     TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern       TEXT NOT NULL,
    category      TEXT NOT NULL,
    weight        REAL DEFAULT 1.0,
    hits          INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    UNIQUE(pattern, category)
);

CREATE TABLE IF NOT EXISTS tags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash     TEXT NOT NULL,
    tag           TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE(file_hash, tag)
);

CREATE TABLE IF NOT EXISTS notes (
    file_hash     TEXT PRIMARY KEY,
    note          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(file_hash);
CREATE INDEX IF NOT EXISTS idx_corrections_hash ON corrections(file_hash);
CREATE INDEX IF NOT EXISTS idx_patterns_pattern ON patterns(pattern);
CREATE INDEX IF NOT EXISTS idx_tags_hash ON tags(file_hash);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CacheEntry:
    file_hash: str
    path: str
    tag: str
    confidence: float
    model: str


class Database:
    def __init__(self, path: str | Path = "data/cache.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- cache -------------------------------------------------------
    def get_cached(self, file_hash: str) -> CacheEntry | None:
        row = self.conn.execute(
            "SELECT * FROM cache WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if not row:
            return None
        return CacheEntry(
            file_hash=row["file_hash"],
            path=row["path"],
            tag=row["tag"],
            confidence=row["confidence"],
            model=row["model"],
        )

    def put_cache(
        self, file_hash: str, path: str, tag: str, confidence: float, model: str
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO cache
               (file_hash, path, tag, confidence, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (file_hash, path, tag, confidence, model, _now()),
        )
        self.conn.commit()

    # ---- corrections -------------------------------------------------
    def add_correction(self, file_hash: str, wrong_tag: str | None, right_tag: str) -> None:
        self.conn.execute(
            """INSERT INTO corrections (file_hash, wrong_tag, right_tag, created_at)
               VALUES (?, ?, ?, ?)""",
            (file_hash, wrong_tag, right_tag, _now()),
        )
        self.conn.commit()

    def get_correction(self, file_hash: str) -> str | None:
        row = self.conn.execute(
            "SELECT right_tag FROM corrections WHERE file_hash = ? ORDER BY id DESC LIMIT 1",
            (file_hash,),
        ).fetchone()
        return row["right_tag"] if row else None

    # ---- patterns ----------------------------------------------------
    def upsert_pattern(self, pattern: str, category: str, weight_delta: float = 0.1) -> None:
        self.conn.execute(
            """INSERT INTO patterns (pattern, category, weight, hits, created_at)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(pattern, category) DO UPDATE SET
                 weight = weight + ?,
                 hits   = hits + 1""",
            (pattern, category, 1.0 + weight_delta, _now(), weight_delta),
        )
        self.conn.commit()

    def lookup_pattern(self, pattern: str) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            "SELECT category, weight FROM patterns WHERE pattern = ?", (pattern,)
        ).fetchall()
        return [(r["category"], r["weight"]) for r in rows]

    # ---- tags --------------------------------------------------------
    def add_tag(self, file_hash: str, tag: str) -> None:
        tag = tag.strip()
        if not tag:
            return
        self.conn.execute(
            """INSERT OR IGNORE INTO tags (file_hash, tag, created_at)
               VALUES (?, ?, ?)""",
            (file_hash, tag, _now()),
        )
        self.conn.commit()

    def set_tags(self, file_hash: str, tags: list[str]) -> None:
        self.conn.execute("DELETE FROM tags WHERE file_hash = ?", (file_hash,))
        for tag in tags:
            tag = tag.strip()
            if tag:
                self.conn.execute(
                    """INSERT OR IGNORE INTO tags (file_hash, tag, created_at)
                       VALUES (?, ?, ?)""",
                    (file_hash, tag, _now()),
                )
        self.conn.commit()

    def get_tags(self, file_hash: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT tag FROM tags WHERE file_hash = ? ORDER BY id", (file_hash,)
        ).fetchall()
        return [r["tag"] for r in rows]

    def all_tags(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT tag FROM tags ORDER BY tag"
        ).fetchall()
        return [r["tag"] for r in rows]

    # ---- notes -------------------------------------------------------
    def set_note(self, file_hash: str, note: str) -> None:
        note = (note or "").strip()
        self.conn.execute("DELETE FROM notes WHERE file_hash = ?", (file_hash,))
        if note:
            self.conn.execute(
                "INSERT INTO notes (file_hash, note, created_at) VALUES (?, ?, ?)",
                (file_hash, note, _now()),
            )
        self.conn.commit()

    def get_note(self, file_hash: str) -> str:
        row = self.conn.execute(
            "SELECT note FROM notes WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row["note"] if row else ""

    def close(self) -> None:
        self.conn.close()