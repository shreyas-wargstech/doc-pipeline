from pathlib import Path

import pytest

from cloud.pipeline_run.source import LocalFolderSource
from shared.exceptions import PipelineError


def _write_pdf(folder: Path, name: str) -> Path:
    p = folder / name
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def test_yields_pdfs_sorted_by_name(tmp_path):
    _write_pdf(tmp_path, "b.pdf")
    _write_pdf(tmp_path, "a.pdf")
    (tmp_path / "notes.txt").write_text("ignore me")
    src = LocalFolderSource(tmp_path)
    items = list(src.iter_documents())
    assert [name for name, _ in items] == ["a.pdf", "b.pdf"]
    assert all(isinstance(path, Path) for _, path in items)


def test_is_non_recursive(tmp_path):
    _write_pdf(tmp_path, "top.pdf")
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_pdf(sub, "nested.pdf")
    src = LocalFolderSource(tmp_path)
    assert [name for name, _ in src.iter_documents()] == ["top.pdf"]


def test_count_matches_iter(tmp_path):
    _write_pdf(tmp_path, "a.pdf")
    _write_pdf(tmp_path, "b.pdf")
    src = LocalFolderSource(tmp_path)
    assert src.count() == 2


def test_missing_folder_raises(tmp_path):
    with pytest.raises(PipelineError):
        LocalFolderSource(tmp_path / "does-not-exist").validate()


def test_path_is_file_raises(tmp_path):
    f = _write_pdf(tmp_path, "a.pdf")
    with pytest.raises(PipelineError):
        LocalFolderSource(f).validate()


def test_no_pdfs_raises(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing here")
    with pytest.raises(PipelineError):
        LocalFolderSource(tmp_path).validate()
