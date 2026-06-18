"""Tests for S3PrefixSource with mocked boto3."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cloud.pipeline_run.source import S3PrefixSource
from shared.exceptions import PipelineError


class _FakePaginator:
    def __init__(self, pages: list[dict]) -> None:
        self._pages = pages

    def paginate(self, **kwargs: Any) -> Any:
        for page in self._pages:
            yield page


def _mock_boto3(keys: list[str]) -> Any:
    """Return a mock boto3 client that lists ``keys`` and downloads to a local file."""
    client = MagicMock()
    pages = [{"Contents": [{"Key": k} for k in keys]}] if keys else []
    client.get_paginator.return_value = _FakePaginator(pages)
    return client


def test_count_and_validate_ok():
    src = S3PrefixSource(bucket="my-bucket", prefix="inbox/")
    with patch("boto3.client", return_value=_mock_boto3(["inbox/a.pdf", "inbox/b.pdf"])):
        assert src.count() == 2
        src.validate()  # does not raise


def test_no_pdfs_raises():
    src = S3PrefixSource(bucket="my-bucket", prefix="inbox/")
    with patch("boto3.client", return_value=_mock_boto3([])):
        with pytest.raises(PipelineError, match="no PDFs found"):
            src.validate()
        assert src.count() == 0


def test_iter_documents_downloads(tmp_path: Path) -> None:
    src = S3PrefixSource(bucket="my-bucket", prefix="inbox/")
    # Pre-seed the resolved keys so we don't need to mock the list call
    src._keys = ["inbox/a.pdf", "inbox/b.pdf"]

    client = MagicMock()

    def fake_download(bucket: str, key: str, filepath: str) -> None:
        Path(filepath).write_bytes(b"%PDF-1.4 fake")

    client.download_file.side_effect = fake_download

    with patch("boto3.client", return_value=client):
        items = list(src.iter_documents())

    assert [name for name, _ in items] == ["a.pdf", "b.pdf"]
    assert all(path.exists() for _, path in items)
    assert src.temp_dir is not None


def test_ignores_non_pdf_keys():
    src = S3PrefixSource(bucket="my-bucket", prefix="inbox/")
    with patch(
        "boto3.client",
        return_value=_mock_boto3(["inbox/a.pdf", "inbox/notes.txt", "inbox/b.pdf"]),
    ):
        assert src.count() == 2


def test_prefix_normalization():
    src = S3PrefixSource(bucket="my-bucket", prefix="inbox")
    assert src.prefix == "inbox/"

    src2 = S3PrefixSource(bucket="my-bucket", prefix="")
    assert src2.prefix == ""
