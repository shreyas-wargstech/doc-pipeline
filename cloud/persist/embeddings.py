"""Sentence-embedding for page summaries.

Lazy-loads the locked multilingual MiniLM model once per process and reuses it.
`.encode` is CPU-bound/sync → offloaded to a worker thread. Output vectors are
unit-normalized (the Qdrant `document_pages` collection is Cosine).
"""
from __future__ import annotations

from typing import Any

import anyio

from shared.config import get_settings
from shared.exceptions import PersistError

_EMBED_DIM = 384
_model: Any = None  # lazy SentenceTransformer singleton


def _get_model() -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(get_settings().embedding_model)
    return _model


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    out = [[float(x) for x in v] for v in vectors]
    for v in out:
        if len(v) != _EMBED_DIM:
            raise PersistError(
                f"embedding dim {len(v)} != expected {_EMBED_DIM} (wrong model?)"
            )
    return out


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings → unit-normalized 384-dim float vectors."""
    if not texts:
        return []
    return await anyio.to_thread.run_sync(_encode_sync, texts)
