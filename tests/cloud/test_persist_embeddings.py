"""Unit tests for cloud/persist/embeddings.py (model mocked)."""
from __future__ import annotations

import numpy as np
import pytest

import cloud.persist.embeddings as emb
from shared.exceptions import PersistError


class _FakeModel:
    def __init__(self, dim=384):
        self.dim = dim

    def encode(self, texts, **kwargs):
        return np.zeros((len(texts), self.dim), dtype="float32")


@pytest.mark.asyncio
async def test_embed_returns_384_dim(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel())
    out = await emb.embed(["a", "b"])
    assert len(out) == 2
    assert all(len(v) == 384 for v in out)
    assert isinstance(out[0][0], float)


@pytest.mark.asyncio
async def test_embed_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel())
    assert await emb.embed([]) == []


@pytest.mark.asyncio
async def test_embed_wrong_dim_raises(monkeypatch):
    monkeypatch.setattr(emb, "_model", _FakeModel(dim=100))
    with pytest.raises(PersistError, match="embedding dim"):
        await emb.embed(["a"])
