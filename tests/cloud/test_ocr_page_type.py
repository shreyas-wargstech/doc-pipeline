"""Unit tests for VlmPageTyper and the shared.page_type re-export."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cloud.ocr.page_type import PAGE_TYPE_CONF_NET, classify_page_type, VlmPageTyper


def test_classify_page_type_reexported():
    # cloud.ocr.page_type re-exports shared.page_type.classify_page_type
    ptype, conf = classify_page_type("Form A application for registration")
    assert ptype == "application_form"
    assert conf >= PAGE_TYPE_CONF_NET


def _fake_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


@pytest.mark.anyio
async def test_vlm_typer_returns_validated_label():
    typer = VlmPageTyper(client=_fake_client("aadhaar"), model="x")
    assert await typer.classify(b"img") == "aadhaar"


@pytest.mark.anyio
async def test_vlm_typer_unknown_label_falls_back_to_other():
    typer = VlmPageTyper(client=_fake_client("a birthday card"), model="x")
    assert await typer.classify(b"img") == "other"
