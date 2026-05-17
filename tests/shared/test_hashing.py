"""Smoke tests for shared.hashing."""
import io

from shared.hashing import hash_bytes, hash_file, hash_stream


def test_hash_bytes_deterministic(sample_pdf_bytes: bytes) -> None:
    assert hash_bytes(sample_pdf_bytes) == hash_bytes(sample_pdf_bytes)


def test_hash_stream_matches_bytes(sample_pdf_bytes: bytes) -> None:
    stream_hash = hash_stream(io.BytesIO(sample_pdf_bytes))
    assert stream_hash == hash_bytes(sample_pdf_bytes)


def test_hash_file_matches_bytes(tmp_path, sample_pdf_bytes: bytes) -> None:
    p = tmp_path / "sample.pdf"
    p.write_bytes(sample_pdf_bytes)
    assert hash_file(p) == hash_bytes(sample_pdf_bytes)


def test_hash_length() -> None:
    assert len(hash_bytes(b"hi")) == 64
