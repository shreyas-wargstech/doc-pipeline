"""Where PDFs come from. ``LocalFolderSource`` ships now; ``S3PrefixSource`` is
a drop-in later with the same ``iter_documents``/``count``/``validate`` contract."""
from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from shared.config import get_settings
from shared.exceptions import PipelineError
from shared.logging import get_logger

log = get_logger(__name__)


@runtime_checkable
class DocumentSource(Protocol):
    """Yields ``(filename, pdf_path)`` for each document to process."""

    def validate(self) -> None:
        """Raise PipelineError if the source is unusable (missing / empty)."""

    def count(self) -> int:
        ...

    def iter_documents(self) -> Iterator[tuple[str, Path]]:
        ...


class LocalFolderSource:
    """Non-recursive enumeration of ``*.pdf`` in a server-side folder, sorted by
    filename for deterministic ordering."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)

    def _pdfs(self) -> list[Path]:
        return sorted(
            (p for p in self.folder.glob("*.pdf") if p.is_file()),
            key=lambda p: p.name,
        )

    def validate(self) -> None:
        if not self.folder.exists():
            raise PipelineError(f"folder does not exist: {self.folder}")
        if not self.folder.is_dir():
            raise PipelineError(f"not a directory: {self.folder}")
        if not self._pdfs():
            raise PipelineError(f"no PDFs found in {self.folder}")

    def count(self) -> int:
        return len(self._pdfs())

    def iter_documents(self) -> Iterator[tuple[str, Path]]:
        for path in self._pdfs():
            yield path.name, path


class S3PrefixSource:
    """Sync enumeration of ``*.pdf`` under an S3 prefix.

    Downloads matching objects to a temporary directory so the rest of the
    pipeline can read them as local files.  Caller should clean up the temp
    directory when the run is finished (``source.temp_dir`` is exposed for
    that).
    """

    def __init__(self, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._keys: list[str] | None = None
        self._temp_dir: Path | None = None

    def _resolve(self) -> list[str]:
        if self._keys is not None:
            return self._keys
        try:
            import boto3
        except ImportError as exc:
            raise PipelineError(
                "boto3 is required for S3PrefixSource; install aioboto3 dependency"
            ) from exc
        s = get_settings()
        kwargs: dict = {"region_name": s.s3_region}
        if s.s3_access_key:
            kwargs["aws_access_key_id"] = s.s3_access_key
        if s.s3_secret_key:
            kwargs["aws_secret_access_key"] = s.s3_secret_key
        if s.s3_endpoint_url:
            kwargs["endpoint_url"] = s.s3_endpoint_url
        client = boto3.client("s3", **kwargs)
        paginator = client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".pdf"):
                    keys.append(key)
        self._keys = sorted(keys)
        return self._keys

    def validate(self) -> None:
        if not self._resolve():
            raise PipelineError(
                f"no PDFs found in s3://{self.bucket}/{self.prefix}"
            )

    def count(self) -> int:
        return len(self._resolve())

    def iter_documents(self) -> Iterator[tuple[str, Path]]:
        keys = self._resolve()
        if not keys:
            return
        import boto3
        s = get_settings()
        kwargs: dict = {"region_name": s.s3_region}
        if s.s3_access_key:
            kwargs["aws_access_key_id"] = s.s3_access_key
        if s.s3_secret_key:
            kwargs["aws_secret_access_key"] = s.s3_secret_key
        if s.s3_endpoint_url:
            kwargs["endpoint_url"] = s.s3_endpoint_url
        client = boto3.client("s3", **kwargs)
        self._temp_dir = Path(tempfile.mkdtemp(prefix="s3prefix_"))
        for key in keys:
            filename = key.split("/")[-1]
            local_path = self._temp_dir / filename
            client.download_file(self.bucket, key, str(local_path))
            yield filename, local_path

    @property
    def temp_dir(self) -> Path | None:
        return self._temp_dir
