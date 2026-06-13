"""Unit tests for cloud/structure/document_type.py."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cloud.structure.document_type import DOCUMENT_TYPES, classify_document_type


def _mock_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def test_document_types_has_54_entries():
    assert len(DOCUMENT_TYPES) == 54
    assert len(set(DOCUMENT_TYPES)) == 54  # no duplicates


@pytest.mark.asyncio
async def test_fuzzy_exact_label_present():
    text = (
        "Maharashtra Council of Homoeopathy\n"
        "Application for: Permanent Registration\n"
        "Name: Ashish Patil"
    )
    assert await classify_document_type(text, client=None) == "Permanent Registration"


@pytest.mark.asyncio
async def test_fuzzy_near_miss_ocr_noise():
    # OCR commonly garbles "ti"->"tl" and drops trailing letters
    text = "Service Applied For: Permanant Registratlon\nDOB: 26/02/1996"
    assert await classify_document_type(text, client=None) == "Permanent Registration"


@pytest.mark.asyncio
async def test_fuzzy_no_match_no_client_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    assert await classify_document_type(text, client=None) is None


@pytest.mark.asyncio
async def test_fuzzy_picks_most_specific_label():
    # "NOC Adjunct OMS 2 Year" should win over the shorter "NOC Permanent
    # Registration" / "Adjunct Maharashtra 2 Year" when its exact text is present
    text = "Application Type: NOC Adjunct OMS 2 Year"
    assert await classify_document_type(text, client=None) == "NOC Adjunct OMS 2 Year"


@pytest.mark.asyncio
async def test_no_fuzzy_match_falls_back_to_llm():
    client = _mock_client("Renewal of Registration")
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=client)
    assert result == "Renewal of Registration"


@pytest.mark.asyncio
async def test_no_fuzzy_match_llm_returns_none():
    client = _mock_client("NONE")
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=client)
    assert result is None


@pytest.mark.asyncio
async def test_fuzzy_match_skips_llm_call_entirely():
    client = _mock_client("Name Change")  # would be wrong if called
    text = "Application for: Permanent Registration"
    result = await classify_document_type(text, client=client)
    assert result == "Permanent Registration"
    client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_no_client_and_no_fuzzy_match_returns_none():
    text = "This page contains no recognizable MCH service label at all."
    result = await classify_document_type(text, client=None)
    assert result is None
