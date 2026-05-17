"""
cloud/classifier/models.py

Output contract for the document classifier.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """
    Returned by ClassifierService.classify().
    Consumed by cloud/ingest/service.py to decide routing.
    """

    document_category: str = Field(
        description="practitioner | letter | receipt | record | other"
    )
    document_type: str | None = Field(
        default=None,
        description=(
            "Fine-grained sub-type within the category. "
            "Examples: 'renewal_application', 'new_registration', "
            "'govt_letter_in', 'sbi_receipt', 'record_book'."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classifier confidence in [0, 1]. < 0.5 → LLM fallback was used.",
    )
    method: str = Field(
        description="'rules' | 'llm' | 'manifest_hint' — which path produced this result."
    )
    signals: list[str] = Field(
        default_factory=list,
        description="Human-readable list of signals that drove the classification.",
    )

    # ---- Routing flags (consumed by service.py) ----------------------------
    match_reference_data: bool = Field(
        default=False,
        description="True only for practitioner category — triggers reference_data lookup.",
    )
    skip_ocr: bool = Field(
        default=False,
        description="True when the cover-page check already tells us the doc needs no OCR "
                    "(e.g. a completely blank bundle — rare).",
    )