"""Pydantic models for inter-stage orchestration messages."""
from __future__ import annotations

from pydantic import BaseModel


class StageMessage(BaseModel):
    """Payload for a per-document stage queue (structure/match/persist).

    Carries only the document_id — every stage reads its inputs from Postgres
    keyed on it. One message == one document.
    """

    schema_version: int = 1
    document_id: str
