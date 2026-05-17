"""Pytest fixtures shared across tests."""
import pytest


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Minimal valid PDF for hashing / upload tests."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f\n"
        b"trailer<</Size 3/Root 1 0 R>>\n"
        b"%%EOF\n"
    )
