"""SHA-256 file hashing with optional fast mode (first 1 MB + size)."""
from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: str | Path, fast: bool = False, chunk_size: int = 1 << 20) -> str:
    """Hash a file. `fast=True` hashes only the first chunk + file size (much faster)."""
    path = Path(path)
    h = hashlib.sha256()
    size = path.stat().st_size

    with path.open("rb") as fh:
        if fast:
            h.update(fh.read(chunk_size))
            h.update(str(size).encode())
        else:
            while chunk := fh.read(chunk_size):
                h.update(chunk)

    return h.hexdigest()