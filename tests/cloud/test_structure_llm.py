# tests/cloud/test_structure_llm.py
"""Unit tests for cloud/structure/llm.py. OpenAI client fully mocked."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import OpenAIError

from cloud.structure.llm import _parse_response, llm_extract
from shared.exceptions import StructureError


class _FakeOpenAIError(OpenAIError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limited")


def _mock_client(content: str | None) -> MagicMock:
    client = MagicMock()
    message = MagicMock(content=content)
    choice = MagicMock(message=message)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


# ---- _parse_response (sync) ------------------------------------------------

def test_parse_good_response():
    raw = (
        '{"page_type":"aadhaar",'
        '"entities":[{"type":"person_name","value":"Ashish","confidence":0.9}],'
        '"identity":{"name":"Ashish","dob":"1996-02-26","gender":"M",'
        '"registration_no":null,"application_number":null}}'
    )
    pt, ents, ident = _parse_response(raw, fallback_page_type="other")
    assert pt == "aadhaar"
    assert ents[0].type == "person_name" and ents[0].source == "llm"
    assert ident == {"name": "Ashish", "dob": "1996-02-26", "gender": "M"}


def test_parse_unknown_page_type_uses_fallback():
    pt, _, _ = _parse_response('{"page_type":"garbage","entities":[],"identity":{}}',
                               fallback_page_type="form")
    assert pt == "form"


def test_parse_unknown_entity_type_becomes_other():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"zzz","value":"x","confidence":0.5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents[0].type == "other"


def test_parse_blank_entity_value_skipped():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"person_name","value":"","confidence":0.5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents == []


def test_parse_null_or_empty_identity_values_dropped():
    _, _, ident = _parse_response(
        '{"page_type":"other","entities":[],'
        '"identity":{"name":"null","dob":null,"gender":"F","registration_no":""}}',
        fallback_page_type="other",
    )
    assert ident == {"gender": "F"}


def test_parse_confidence_clamped():
    _, ents, _ = _parse_response(
        '{"page_type":"other","entities":[{"type":"date","value":"x","confidence":5}],'
        '"identity":{}}',
        fallback_page_type="other",
    )
    assert ents[0].confidence == pytest.approx(1.0)


def test_parse_malformed_returns_fallback_tuple():
    pt, ents, ident = _parse_response("not json at all", fallback_page_type="ssc")
    assert pt == "ssc" and ents == [] and ident == {}


def test_parse_json_in_markdown_fence():
    raw = '```json\n{"page_type":"hsc","entities":[],"identity":{}}\n```'
    pt, _, _ = _parse_response(raw, fallback_page_type="other")
    assert pt == "hsc"


# ---- llm_extract (async) ---------------------------------------------------

@pytest.mark.asyncio
async def test_llm_extract_happy_path():
    client = _mock_client('{"page_type":"hsc","entities":[],"identity":{}}')
    pt, ents, ident = await llm_extract(
        "page text", document_category="practitioner", page_type="other", client=client
    )
    assert pt == "hsc" and ents == [] and ident == {}


@pytest.mark.asyncio
async def test_llm_extract_api_error_raises_structure_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = _FakeOpenAIError()
    with pytest.raises(StructureError, match="rate limited"):
        await llm_extract("t", document_category="practitioner", page_type="other",
                          client=client)


@pytest.mark.asyncio
async def test_llm_extract_malformed_returns_fallback_page_type():
    client = _mock_client("sorry, cannot read this")
    pt, ents, ident = await llm_extract(
        "t", document_category="practitioner", page_type="form", client=client
    )
    assert pt == "form" and ents == [] and ident == {}


@pytest.mark.asyncio
async def test_llm_extract_no_key_raises():
    with patch("cloud.structure.llm.get_settings") as ms:
        ms.return_value.openrouter_api_key = None
        with pytest.raises(StructureError, match="OPENROUTER_API_KEY"):
            await llm_extract("t", document_category="practitioner", page_type="other")


@pytest.mark.asyncio
async def test_llm_extract_offloads_to_thread():
    client = _mock_client('{"page_type":"other","entities":[],"identity":{}}')
    with patch("anyio.to_thread.run_sync", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ("other", [], {})
        await llm_extract("t", document_category="practitioner", page_type="other",
                          client=client)
    mock_run.assert_awaited_once()
