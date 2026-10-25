# File: src/file_categorizer/core/duplicates.py
"""
duplicates.py
=============

Library-wide duplicate discovery in the style of Lap's indexer:

* exact groups come from full SHA-256 hashes plus ``meta_file_locations`` so
  byte-identical copies in different folders collapse into one group;
* perceptual groups use the stored pHash values and complete-link clustering,
  which avoids the chaining problem of single-link grouping (A~B, B~C does not
  force A~C into the same group);
* nothing is deleted.  Each group only gets a suggested "keep" file and a
  reclaimable byte count for the GUI/CLI to present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .metadata_db import MetadataDatabase

logger = logging.getLogger(__name__)

DEFAULT_PHASH_THRESHOLD = 6
DEFAULT_MAX_GROUP_SIZE = 64


@dataclass
class DuplicateFile:
    file_hash: str
    file_path: str
    file_size: int = 0
    first_seen: str = ""
    taken_date: str = ""
    phash: str | None = None
    is_keep: bool = False
    similarity: float | None = None


@dataclass
class DuplicateGroup:
    group_id: str
    kind: str  # "exact" | "perceptual"
    files: list[DuplicateFile] = field(default_factory=list)
    keep_path: str = ""

    @property
    def total_size(self) -> int:
        return sum(max(0, f.file_size) for f in self.files)

    @property
    def reclaimable(self) -> int:
        keep = next((f for f in self.files if f.is_keep), None)
        keep_size = max(0, keep.file_size) if keep else 0
        return max(0, self.total_size - keep_size)


def _hamming(left: str, right: str) -> int:
    try:
        return bin(int(left, 16) ^ int(right, 16)).count("1")
    except (TypeError, ValueError):
        return 10_000


def _dedupe_paths(files: list[DuplicateFile]) -> list[DuplicateFile]:
    seen: set[str] = set()
    result: list[DuplicateFile] = []
    for f in files:
        key = f.file_path.replace("/", "\\").lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(f)
    return result


def _location_entries(
    mdb: MetadataDatabase,
) -> dict[str, list[DuplicateFile]]:
    """Group every recorded physical location by content hash."""
    files = {row["file_hash"]: row for row in mdb.all_files()}
    locations = mdb.all_locations()
    by_hash: dict[str, list[DuplicateFile]] = {}
    taken_dates: dict[str, str] = {}

    for row in locations:
        file_hash = row["file_hash"]
        path = row["file_path"]
        if not path:
            continue
        meta = files.get(file_hash)
        if file_hash not in taken_dates:
            taken = mdb.get_field_value(file_hash, "taken_date") or ""
            taken_dates[file_hash] = str(taken)
        phash = row["phash"]
        if not phash:
            phash = mdb.get_field_value(file_hash, "phash")
        if not phash:
            stored = mdb.get_enrichment(f"phash:{file_hash}")
            phash = stored.get("phash") if stored else None
        by_hash.setdefault(file_hash, []).append(DuplicateFile(
            file_hash=file_hash,
            file_path=str(path),
            file_size=int(row["file_size"] or 0),
            first_seen=str(row["first_seen"] or ""),
            taken_date=taken_dates[file_hash],
            phash=str(phash) if phash else None,
        ))

    # Older databases may predate meta_file_locations.  Still surface their
    # metadata rows so the UI does not look empty.
    for file_hash, row in files.items():
        if file_hash in by_hash:
            continue
        path = row["moved_to"] or row["file_path"]
        if not path:
            continue
        phash = mdb.get_field_value(file_hash, "phash")
        if not phash:
            stored = mdb.get_enrichment(f"phash:{file_hash}")
            phash = stored.get("phash") if stored else None
        by_hash[file_hash] = [DuplicateFile(
            file_hash=file_hash,
            file_path=str(path),
            first_seen=str(row["first_seen"] or ""),
            taken_date=str(mdb.get_field_value(file_hash, "taken_date") or ""),
            phash=str(phash) if phash else None,
        )]

    return by_hash


def _pick_keep(files: list[DuplicateFile]) -> DuplicateFile:
    """Prefer the oldest indexed copy; break ties by path for determinism."""
    return sorted(files, key=lambda f: (f.first_seen or "9999", f.file_path))[0]


def _mark_keep(files: list[DuplicateFile], keep: DuplicateFile) -> None:
    for f in files:
        f.is_keep = f is keep
    files.sort(key=lambda f: (not f.is_keep, f.file_path))


def _exact_groups(
    by_hash: dict[str, list[DuplicateFile]],
) -> tuple[list[DuplicateGroup], set[str]]:
    groups: list[DuplicateGroup] = []
    exact_hashes: set[str] = set()
    for file_hash, entries in by_hash.items():
        entries = _dedupe_paths(entries)
        if len(entries) < 2:
            continue
        exact_hashes.add(file_hash)
        keep = _pick_keep(entries)
        for entry in entries:
            entry.similarity = 1.0
        _mark_keep(entries, keep)
        groups.append(DuplicateGroup(
            group_id=f"exact-{file_hash[:12]}",
            kind="exact",
            files=entries,
            keep_path=keep.file_path,
        ))
    return groups, exact_hashes


def _perceptual_groups(
    by_hash: dict[str, list[DuplicateFile]],
    exclude_hashes: set[str],
    threshold: int,
    max_group_size: int,
) -> list[DuplicateGroup]:
    items = [
        entries[0]
        for file_hash, entries in by_hash.items()
        if file_hash not in exclude_hashes and entries and entries[0].phash
    ]
    if len(items) < 2:
        return []

    n = len(items)
    distances: dict[tuple[int, int], int] = {}
    edges: list[tuple[int, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            dist = _hamming(items[i].phash or "", items[j].phash or "")
            if dist <= threshold:
                distances[(i, j)] = dist
                edges.append((dist, i, j))

    parent = list(range(n))
    members: dict[int, set[int]] = {i: {i} for i in range(n)}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def distance(a: int, b: int) -> int:
        if a == b:
            return 0
        return distances.get((min(a, b), max(a, b)), 10_000)

    for _, i, j in sorted(edges):
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        if len(members[ri]) + len(members[rj]) > max_group_size:
            continue
        # Complete-link: every cross pair must also be similar.  This is what
        # stops a chain of near-matches from merging unrelated images.
        if all(distance(a, b) <= threshold
               for a in members[ri] for b in members[rj]):
            if len(members[ri]) < len(members[rj]):
                ri, rj = rj, ri
            parent[rj] = ri
            members[ri] |= members.pop(rj)

    groups: list[DuplicateGroup] = []
    for root, member_ids in members.items():
        if len(member_ids) < 2:
            continue
        group_files = [items[i] for i in sorted(member_ids)]
        keep = _representative(group_files)
        for f in group_files:
            f.similarity = (
                1.0 if f is keep
                else 1.0 - (_hamming(f.phash or "", keep.phash or "") / 64.0)
            )
        _mark_keep(group_files, keep)
        groups.append(DuplicateGroup(
            group_id=f"perceptual-{keep.file_hash[:12]}",
            kind="perceptual",
            files=group_files,
            keep_path=keep.file_path,
        ))
    return groups


def _representative(files: list[DuplicateFile]) -> DuplicateFile:
    """Pick the image closest to all others (Lap's representative heuristic)."""
    best = files[0]
    best_score = -1.0
    for candidate in files:
        scores = [
            1.0 - (_hamming(candidate.phash or "", other.phash or "") / 64.0)
            for other in files if other is not candidate
        ]
        avg = sum(scores) / len(scores) if scores else 0.0
        if avg > best_score:
            best, best_score = candidate, avg
    return best


def scan_duplicates(
    mdb: MetadataDatabase,
    phash_threshold: int = DEFAULT_PHASH_THRESHOLD,
    include_perceptual: bool = True,
    max_group_size: int = DEFAULT_MAX_GROUP_SIZE,
) -> list[DuplicateGroup]:
    """Return exact and perceptual duplicate groups, largest wins first."""
    by_hash = _location_entries(mdb)
    exact, exact_hashes = _exact_groups(by_hash)
    perceptual: list[DuplicateGroup] = []
    if include_perceptual:
        try:
            perceptual = _perceptual_groups(
                by_hash, exact_hashes, int(phash_threshold),
                max(2, int(max_group_size)),
            )
        except Exception as exc:
            logger.warning("perceptual duplicate scan skipped: %s", exc)

    groups = exact + perceptual
    groups.sort(key=lambda g: (-g.reclaimable, g.kind, g.group_id))
    return groups


def group_summary(groups: list[DuplicateGroup]) -> dict[str, Any]:
    return {
        "groups": len(groups),
        "exact_groups": sum(1 for g in groups if g.kind == "exact"),
        "perceptual_groups": sum(1 for g in groups if g.kind == "perceptual"),
        "files": sum(len(g.files) for g in groups),
        "reclaimable": sum(g.reclaimable for g in groups),
    }
