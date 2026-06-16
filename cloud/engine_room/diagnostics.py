"""Diagnostic tools for the Engine Room.

Safe, read-only checks that report system integrity and connectivity.
Never crash — every check returns a result, even on failure.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from sqlalchemy import text

from shared.config import get_settings
from shared.db import session_scope
from shared.logging import get_logger

log = get_logger(__name__)

DIAGNOSTIC_TIMEOUT = 5.0


@dataclass
class DiagnosticResult:
    name: str
    status: str  # "pass" | "fail" | "error"
    detail: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "error": self.error,
        }


async def check_db_integrity() -> DiagnosticResult:
    """Check for orphaned pages, docs without pages, and count totals."""
    try:
        async with session_scope() as session:
            # Orphaned pages: pages whose document_id doesn't exist in documents
            orphaned = await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM pages p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM documents d WHERE d.document_id = p.document_id
                    )
                    """
                )
            )
            orphaned_count = orphaned.scalar()

            # Documents without pages
            empty_docs = await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM documents d
                    WHERE NOT EXISTS (
                        SELECT 1 FROM pages p WHERE p.document_id = d.document_id
                    )
                    """
                )
            )
            empty_docs_count = empty_docs.scalar()

            # Totals
            total_docs = await session.execute(text("SELECT COUNT(*) FROM documents"))
            total_pages = await session.execute(text("SELECT COUNT(*) FROM pages"))

            doc_n = total_docs.scalar()
            page_n = total_pages.scalar()

            issues: list[str] = []
            if orphaned_count:
                issues.append(f"{orphaned_count} orphaned pages")
            if empty_docs_count:
                issues.append(f"{empty_docs_count} documents without pages")

            if issues:
                return DiagnosticResult(
                    name="db_integrity",
                    status="fail",
                    detail=f"{doc_n} documents, {page_n} pages. Issues: {', '.join(issues)}.",
                    error="; ".join(issues),
                )

            return DiagnosticResult(
                name="db_integrity",
                status="pass",
                detail=f"{doc_n} documents, {page_n} pages. No integrity issues.",
            )
    except Exception as exc:  # noqa: BLE001
        return DiagnosticResult(
            name="db_integrity",
            status="error",
            detail="Could not run integrity check.",
            error=str(exc),
        )


async def test_openrouter_connection() -> DiagnosticResult:
    """Ping OpenRouter API to verify connectivity and key validity."""
    try:
        settings = get_settings()
        if not settings.openrouter_api_key:
            return DiagnosticResult(
                name="openrouter_connection",
                status="fail",
                detail="OPENROUTER_API_KEY not configured.",
                error="API key missing",
            )

        async with httpx.AsyncClient(timeout=DIAGNOSTIC_TIMEOUT) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            model_count = len(data.get("data", []))

            return DiagnosticResult(
                name="openrouter_connection",
                status="pass",
                detail=f"Connected. {model_count} models available.",
            )
    except Exception as exc:  # noqa: BLE001
        return DiagnosticResult(
            name="openrouter_connection",
            status="fail",
            detail="OpenRouter connection failed.",
            error=str(exc),
        )


async def test_tesseract_connection() -> DiagnosticResult:
    """Verify Tesseract is installed and responsive."""
    try:
        import pytesseract
        version = await anyio.to_thread.run_sync(pytesseract.get_tesseract_version)
        return DiagnosticResult(
            name="tesseract_connection",
            status="pass",
            detail=f"Tesseract {version} installed.",
        )
    except Exception as exc:  # noqa: BLE001
        return DiagnosticResult(
            name="tesseract_connection",
            status="fail",
            detail="Tesseract not available.",
            error=str(exc),
        )


async def run_diagnostics() -> list[DiagnosticResult]:
    """Run all diagnostic checks in parallel."""
    results = await asyncio.gather(
        check_db_integrity(),
        test_openrouter_connection(),
        test_tesseract_connection(),
        return_exceptions=True,
    )

    out: list[DiagnosticResult] = []
    for r in results:
        if isinstance(r, Exception):
            out.append(DiagnosticResult(name="unknown", status="error", detail="Crash", error=str(r)))
        else:
            out.append(r)
    return out
