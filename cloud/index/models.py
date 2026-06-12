"""Pydantic models for the index stage."""
from __future__ import annotations

from pydantic import BaseModel, field_validator

ENTITY_TYPES = frozenset({
    "practitioner",
    "organization",
    "vendor",
    "government_body",
    "educational_institute",
    "hospital",
})


class IndexedEntity(BaseModel):
    type: str
    value: str
    confidence: float

    @field_validator("type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type: {v!r}. Must be one of {sorted(ENTITY_TYPES)}")
        return v


class PageIndexResult(BaseModel):
    page_id: str
    summary: str | None
    keywords: list[str]
    entities: list[IndexedEntity]


class DocumentIndexResult(BaseModel):
    document_id: str
    summary: str | None
    page_results: list[PageIndexResult]
