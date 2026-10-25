# File: src/file_categorizer/core/metadata_db.py
"""
metadata_db.py
==============

PURPOSE
-------
Adds the new SQLite tables required by the metadata + spreadsheet system,
without touching the existing Database class in core/db.py.

It opens its own connection to the SAME SQLite file (data/cache.db) so
that both the existing Database (cache/corrections/patterns/tags/notes)
and this MetadataDatabase (files/extracted_fields/entities/...) can
coexist safely.

WHY A SEPARATE MODULE?
----------------------
The existing Database class is used by the GUI worker thread and is
opened with check_same_thread=False. To avoid breaking anything, we do
NOT modify db.py. Instead, this module:
  - creates the new tables if they do not exist,
  - exposes simple get/put methods,
  - uses its own short-lived connections per call (safe for threads).

HOW TO COMBINE WITH MAIN PROGRAM
--------------------------------
1. Copy this file into src/file_categorizer/core/.
2. In the new metadata pipeline (core/metadata_pipeline.py), import:
       from .metadata_db import MetadataDatabase
3. Instantiate once:
       mdb = MetadataDatabase(cfg.paths.get("database", "data/cache.db"))
4. Call mdb.init_schema() at startup.
5. Use mdb.put_file(...), mdb.put_field(...), etc. after extraction.

NOTES FOR OTHER AI AGENTS
-------------------------
- Do NOT rename or restructure the existing tables (cache, corrections,
  patterns, tags, notes). They belong to core/db.py.
- All new tables use IF NOT EXISTS so re-running is safe.
- Table names are prefixed "meta_" to avoid clashes.
- The file_hash column is the SHA-256 from core/hasher.py (fast mode).
- Nullable columns are used where the field may not exist for a file.
- The "source" column in extracted_fields is a string:
     image | caption | comment | ocr | search | manual
- The "correlation" column in extracted_fields is:
     high | medium | low | none
- The "entity_type" column in entities is a string:
     anime | movie_tv | website | url | account | song | artist | platform
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# These CREATE statements are additive. They do not modify existing tables.
# ---------------------------------------------------------------------------

META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_files (
    file_hash        TEXT PRIMARY KEY,
    file_path        TEXT NOT NULL,
    original_path    TEXT,
    category         TEXT,
    subcategory      TEXT,
    platform         TEXT,
    moved_to         TEXT,
    thumbnail_path   TEXT,
    first_seen       TEXT NOT NULL,
    last_updated     TEXT NOT NULL,
    needs_review     INTEGER DEFAULT 0,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS meta_extracted_fields (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash        TEXT NOT NULL,
    field_name       TEXT NOT NULL,
    field_value      TEXT,
    source           TEXT,
    confidence       REAL,
    evidence         TEXT,
    correlation      TEXT,
    model_used       TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE(file_hash, field_name, field_value)
);

CREATE TABLE IF NOT EXISTS meta_entities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT NOT NULL,
    entity_value     TEXT NOT NULL,
    display_name     TEXT,
    platform         TEXT,
    url              TEXT,
    bio_summary      TEXT,
    content_type     TEXT,
    confidence       REAL,
    first_seen       TEXT NOT NULL,
    last_updated     TEXT NOT NULL,
    UNIQUE(entity_type, entity_value)
);

CREATE TABLE IF NOT EXISTS meta_file_entities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash        TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    role             TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE(file_hash, entity_id, role)
);

CREATE TABLE IF NOT EXISTS meta_file_locations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash        TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    original_path    TEXT,
    file_size        INTEGER,
    modified_at      REAL,
    phash            TEXT,
    first_seen       TEXT NOT NULL,
    last_updated     TEXT NOT NULL,
    UNIQUE(file_hash, file_path)
);

CREATE TABLE IF NOT EXISTS meta_enrichment_cache (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    query_key        TEXT NOT NULL UNIQUE,
    query_type       TEXT NOT NULL,
    response_json    TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    last_used        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_field_corrections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash        TEXT,
    entity_type      TEXT,
    entity_value     TEXT,
    field_name       TEXT NOT NULL,
    wrong_value      TEXT,
    right_value      TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_exports (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    workbook_path    TEXT NOT NULL,
    sheet_count      INTEGER,
    row_count        INTEGER,
    exported_at      TEXT NOT NULL,
    notes            TEXT
);

CREATE INDEX IF NOT EXISTS idx_meta_fields_hash
    ON meta_extracted_fields(file_hash);
CREATE INDEX IF NOT EXISTS idx_meta_fields_name
    ON meta_extracted_fields(field_name);
CREATE INDEX IF NOT EXISTS idx_meta_entities_type
    ON meta_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_meta_entities_value
    ON meta_entities(entity_value);
CREATE INDEX IF NOT EXISTS idx_meta_file_entities_hash
    ON meta_file_entities(file_hash);
CREATE INDEX IF NOT EXISTS idx_meta_locations_hash
    ON meta_file_locations(file_hash);
CREATE INDEX IF NOT EXISTS idx_meta_locations_path
    ON meta_file_locations(file_path);
CREATE INDEX IF NOT EXISTS idx_meta_corrections_hash
    ON meta_field_corrections(file_hash);
"""


# ---------------------------------------------------------------------------
# Row dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MetaFile:
    file_hash: str
    file_path: str
    original_path: str | None = None
    category: str | None = None
    subcategory: str | None = None
    platform: str | None = None
    moved_to: str | None = None
    thumbnail_path: str | None = None
    first_seen: str = ""
    last_updated: str = ""
    needs_review: bool = False
    notes: str | None = None


@dataclass
class MetaField:
    file_hash: str
    field_name: str
    field_value: str | None
    source: str | None = None
    confidence: float | None = None
    evidence: str | None = None
    correlation: str | None = None
    model_used: str | None = None


@dataclass
class MetaEntity:
    entity_type: str
    entity_value: str
    display_name: str | None = None
    platform: str | None = None
    url: str | None = None
    bio_summary: str | None = None
    content_type: str | None = None
    confidence: float | None = None


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class MetadataDatabase:
    """
    Additive SQLite layer for metadata extraction.

    Uses a fresh connection per call for thread safety. The main
    Database class in core/db.py keeps its own connection; both point
    at the same file.
    """

    def __init__(self, path: str | Path = "data/cache.db") -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    # -- low level ---------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(META_SCHEMA)

    def count_rows(self, table: str) -> int:
        """Count rows in a meta_* table (guards against SQL injection)."""
        if not table.startswith("meta_") or not table.replace("_", "").isalnum():
            raise ValueError(f"not a metadata table: {table!r}")
        with self._conn() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # -- meta_files --------------------------------------------------------

    def upsert_file(self, f: MetaFile) -> None:
        now = _now()
        if not f.first_seen:
            f.first_seen = now
        f.last_updated = now
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_files
                  (file_hash, file_path, original_path, category, subcategory,
                   platform, moved_to, thumbnail_path, first_seen,
                   last_updated, needs_review, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_hash) DO UPDATE SET
                  file_path=excluded.file_path,
                  original_path=COALESCE(excluded.original_path, meta_files.original_path),
                  category=COALESCE(excluded.category, meta_files.category),
                  subcategory=COALESCE(excluded.subcategory, meta_files.subcategory),
                  platform=COALESCE(excluded.platform, meta_files.platform),
                  moved_to=COALESCE(excluded.moved_to, meta_files.moved_to),
                  thumbnail_path=COALESCE(excluded.thumbnail_path, meta_files.thumbnail_path),
                  last_updated=excluded.last_updated,
                  needs_review=excluded.needs_review,
                  notes=COALESCE(excluded.notes, meta_files.notes)
                """,
                (
                    f.file_hash, f.file_path, f.original_path, f.category,
                    f.subcategory, f.platform, f.moved_to, f.thumbnail_path,
                    f.first_seen, f.last_updated, int(f.needs_review), f.notes,
                ),
            )

    def get_file(self, file_hash: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_files WHERE file_hash = ?", (file_hash,)
            )
            return cur.fetchone()

    def file_exists(self, file_hash: str) -> bool:
        return self.get_file(file_hash) is not None

    def all_files(self) -> list[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM meta_files ORDER BY first_seen DESC")
            return cur.fetchall()

    # -- physical file locations ------------------------------------------
    #
    # meta_files is keyed by content hash, so two byte-identical files collapse
    # into one metadata row.  meta_file_locations keeps every path we have seen
    # for that hash.  That is what makes exact-duplicate groups possible without
    # duplicating the extracted metadata.

    def record_location(
        self,
        file_hash: str,
        file_path: str,
        original_path: str | None = None,
        file_size: int | None = None,
        modified_at: float | None = None,
        phash: str | None = None,
    ) -> None:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_file_locations
                  (file_hash, file_path, original_path, file_size, modified_at,
                   phash, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_hash, file_path) DO UPDATE SET
                  original_path=COALESCE(excluded.original_path,
                                         meta_file_locations.original_path),
                  file_size=COALESCE(excluded.file_size,
                                     meta_file_locations.file_size),
                  modified_at=COALESCE(excluded.modified_at,
                                       meta_file_locations.modified_at),
                  phash=COALESCE(excluded.phash, meta_file_locations.phash),
                  last_updated=excluded.last_updated
                """,
                (
                    file_hash, str(file_path), original_path, file_size,
                    modified_at, phash, now, now,
                ),
            )

    def all_locations(self) -> list[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_file_locations ORDER BY file_hash, id"
            )
            return cur.fetchall()

    def get_locations(self, file_hash: str) -> list[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_file_locations "
                "WHERE file_hash = ? ORDER BY id",
                (file_hash,),
            )
            return cur.fetchall()

    def location_for_path(self, file_path: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_file_locations WHERE file_path = ? "
                "ORDER BY id DESC LIMIT 1",
                (str(file_path),),
            )
            return cur.fetchone()

    def find_location_by_hash(
        self, file_hash: str, exclude_path: str | None = None
    ) -> sqlite3.Row | None:
        """Return one other path that has the same content hash, if any."""
        with self._conn() as conn:
            if exclude_path:
                cur = conn.execute(
                    "SELECT * FROM meta_file_locations "
                    "WHERE file_hash = ? AND file_path <> ? LIMIT 1",
                    (file_hash, str(exclude_path)),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM meta_file_locations "
                    "WHERE file_hash = ? LIMIT 1",
                    (file_hash,),
                )
            return cur.fetchone()

    def remove_location(self, file_path: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM meta_file_locations WHERE file_path = ?",
                (str(file_path),),
            )

    def move_location(self, old_path: str, new_path: str,
                      original_path: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE meta_file_locations
                   SET file_path = ?,
                       original_path = COALESCE(?, original_path),
                       last_updated = ?
                 WHERE file_path = ?
                """,
                (str(new_path), original_path, _now(), str(old_path)),
            )

    # -- extracted fields --------------------------------------------------

    def put_field(self, f: MetaField) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_extracted_fields
                  (file_hash, field_name, field_value, source, confidence,
                   evidence, correlation, model_used, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_hash, field_name, field_value) DO UPDATE SET
                  source=COALESCE(excluded.source, meta_extracted_fields.source),
                  confidence=COALESCE(excluded.confidence, meta_extracted_fields.confidence),
                  evidence=COALESCE(excluded.evidence, meta_extracted_fields.evidence),
                  correlation=COALESCE(excluded.correlation, meta_extracted_fields.correlation),
                  model_used=COALESCE(excluded.model_used, meta_extracted_fields.model_used)
                """,
                (
                    f.file_hash, f.field_name, f.field_value, f.source,
                    f.confidence, f.evidence, f.correlation, f.model_used,
                    _now(),
                ),
            )

    def put_fields(self, fields: Iterable[MetaField]) -> None:
        for f in fields:
            self.put_field(f)

    def get_fields(self, file_hash: str) -> list[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_extracted_fields WHERE file_hash = ? ORDER BY id",
                (file_hash,),
            )
            return cur.fetchall()

    def get_field_names(self, file_hash: str) -> set[str]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT DISTINCT field_name FROM meta_extracted_fields "
                "WHERE file_hash = ?",
                (file_hash,),
            )
            return {row["field_name"] for row in cur.fetchall()}

    def get_field_value(self, file_hash: str, field_name: str) -> str | None:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT field_value FROM meta_extracted_fields
                WHERE file_hash = ? AND field_name = ?
                ORDER BY confidence DESC, id DESC LIMIT 1
                """,
                (file_hash, field_name),
            )
            row = cur.fetchone()
            return row["field_value"] if row else None

    # -- entities ----------------------------------------------------------

    def upsert_entity(self, e: MetaEntity) -> int:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_entities
                  (entity_type, entity_value, display_name, platform, url,
                   bio_summary, content_type, confidence, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_value) DO UPDATE SET
                  display_name=COALESCE(excluded.display_name, meta_entities.display_name),
                  platform=COALESCE(excluded.platform, meta_entities.platform),
                  url=COALESCE(excluded.url, meta_entities.url),
                  bio_summary=COALESCE(excluded.bio_summary, meta_entities.bio_summary),
                  content_type=COALESCE(excluded.content_type, meta_entities.content_type),
                  confidence=COALESCE(excluded.confidence, meta_entities.confidence),
                  last_updated=excluded.last_updated
                """,
                (
                    e.entity_type, e.entity_value, e.display_name, e.platform,
                    e.url, e.bio_summary, e.content_type, e.confidence,
                    now, now,
                ),
            )
            cur = conn.execute(
                "SELECT id FROM meta_entities WHERE entity_type=? AND entity_value=?",
                (e.entity_type, e.entity_value),
            )
            row = cur.fetchone()
            return int(row["id"]) if row else -1

    def get_entity(self, entity_type: str, entity_value: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM meta_entities WHERE entity_type=? AND entity_value=?",
                (entity_type, entity_value),
            )
            return cur.fetchone()

    def all_entities(self, entity_type: str | None = None) -> list[sqlite3.Row]:
        with self._conn() as conn:
            if entity_type:
                cur = conn.execute(
                    "SELECT * FROM meta_entities WHERE entity_type=? ORDER BY id",
                    (entity_type,),
                )
            else:
                cur = conn.execute("SELECT * FROM meta_entities ORDER BY id")
            return cur.fetchall()

    # -- file <-> entity link ---------------------------------------------

    def link_file_entity(
        self, file_hash: str, entity_id: int, role: str | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO meta_file_entities
                  (file_hash, entity_id, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (file_hash, entity_id, role, _now()),
            )

    def get_file_entities(self, file_hash: str) -> list[sqlite3.Row]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT e.*, fe.role FROM meta_entities e
                JOIN meta_file_entities fe ON fe.entity_id = e.id
                WHERE fe.file_hash = ?
                ORDER BY e.id
                """,
                (file_hash,),
            )
            return cur.fetchall()

    # -- enrichment cache --------------------------------------------------

    def get_enrichment(self, query_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT response_json FROM meta_enrichment_cache WHERE query_key=?",
                (query_key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE meta_enrichment_cache SET last_used=? WHERE query_key=?",
                (_now(), query_key),
            )
            try:
                return json.loads(row["response_json"])
            except Exception:
                return None

    def put_enrichment(self, query_key: str, query_type: str, data: dict[str, Any]) -> None:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_enrichment_cache
                  (query_key, query_type, response_json, created_at, last_used)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                  response_json=excluded.response_json,
                  last_used=excluded.last_used
                """,
                (query_key, query_type, json.dumps(data), now, now),
            )

    # -- field corrections -------------------------------------------------

    def add_field_correction(
        self,
        field_name: str,
        right_value: str,
        wrong_value: str | None = None,
        file_hash: str | None = None,
        entity_type: str | None = None,
        entity_value: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_field_corrections
                  (file_hash, entity_type, entity_value, field_name,
                   wrong_value, right_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash, entity_type, entity_value, field_name,
                    wrong_value, right_value, _now(),
                ),
            )

    def get_field_correction_for_hash(
        self, file_hash: str, field_name: str
    ) -> str | None:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT right_value FROM meta_field_corrections
                WHERE file_hash=? AND field_name=?
                ORDER BY id DESC LIMIT 1
                """,
                (file_hash, field_name),
            )
            row = cur.fetchone()
            return row["right_value"] if row else None

    def get_field_correction_for_entity(
        self, entity_type: str, entity_value: str, field_name: str
    ) -> str | None:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT right_value FROM meta_field_corrections
                WHERE entity_type=? AND entity_value=? AND field_name=?
                ORDER BY id DESC LIMIT 1
                """,
                (entity_type, entity_value, field_name),
            )
            row = cur.fetchone()
            return row["right_value"] if row else None

    def get_hash_field_corrections(self, file_hash: str) -> dict[str, str]:
        """Latest correction per field_name for a specific file hash."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT field_name, right_value FROM meta_field_corrections
                WHERE file_hash=? ORDER BY id
                """,
                (file_hash,),
            )
            return {r["field_name"]: r["right_value"] for r in cur.fetchall()}

    def get_entity_field_corrections(
        self, entity_type: str, entity_value: str
    ) -> dict[str, str]:
        """Latest correction per field_name for a specific entity."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT field_name, right_value FROM meta_field_corrections
                WHERE entity_type=? AND entity_value=? ORDER BY id
                """,
                (entity_type, entity_value),
            )
            return {r["field_name"]: r["right_value"] for r in cur.fetchall()}

    # -- exports -----------------------------------------------------------

    def log_export(self, workbook_path: str, sheet_count: int,
                   row_count: int, notes: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meta_exports
                  (workbook_path, sheet_count, row_count, exported_at, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workbook_path, sheet_count, row_count, _now(), notes),
            )