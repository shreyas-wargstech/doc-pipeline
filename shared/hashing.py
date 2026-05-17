"""Stream-based content hashing.

document_id = sha256(original PDF), computed once on the NAS and trusted
downstream. Stream-based so we never load the whole file into memory.
"""
import hashlib
from pathlib import Path
from typing import BinaryIO

_CHUNK = 1024 * 1024  # 1 MiB


def hash_stream(stream: BinaryIO) -> str:
    """Compute sha256 hex digest of a binary stream."""
    h = hashlib.sha256()
    while chunk := stream.read(_CHUNK):
        h.update(chunk)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    """Compute sha256 hex digest of an in-memory bytes object."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    """Compute sha256 hex digest of a file on disk."""
    with open(path, "rb") as f:
        return hash_stream(f)
