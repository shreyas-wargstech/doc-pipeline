"""Where PDFs come from. ``LocalFolderSource`` ships now; ``S3PrefixSource`` is
a drop-in later with the same ``iter_documents``/``count``/``validate`` contract."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from shared.exceptions import PipelineError


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
