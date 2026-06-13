# A4: Multi-application-form-page VLM selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure only the first (`page_num`-earliest) `application_form`-typed page in a bundle gets manifest `page_type="form"` (and therefore the paid VLM-first OCR path); any later pages that also classify as `application_form` are demoted to `"other"`.

**Architecture:** Single post-process step in `nas/uploader/service.py::upload_document`, after the existing per-page loop builds `pages: list[PageManifest]` and before `Manifest(...)` is constructed. No new files, no schema change, no router change.

**Tech Stack:** Python 3.13, pydantic v2 (`PageManifest.model_copy`), pytest + pytest-asyncio (existing `tests/nas/test_uploader_service.py` patterns).

---

### Task 1: Demote non-first `"form"` pages to `"other"`

**Files:**
- Modify: `nas/uploader/service.py:96-104`
- Test: `tests/nas/test_uploader_service.py`

- [ ] **Step 1: Write the failing test**

Add this fixture and test to `tests/nas/test_uploader_service.py` (after `patched_with_form`, before `test_form_page_detected_via_keyword_match`):

```python
@pytest.fixture
def patched_with_two_forms(monkeypatch):
    """4 pages: page 1 application-form text, page 2 unrelated text,
    page 3 ALSO application-form text (e.g. a continuation/second form),
    page 4 blank."""
    imgs = [
        np.full((50, 50), 255, np.uint8),
        np.full((50, 50), 254, np.uint8),
        np.full((50, 50), 253, np.uint8),
        np.full((50, 50), 252, np.uint8),
    ]
    monkeypatch.setattr(svc, "render_pdf", lambda path, *, dpi: imgs)

    results = [
        PreprocessResult(image=imgs[0], triage=_triage()),
        PreprocessResult(image=imgs[1], triage=_triage()),
        PreprocessResult(image=imgs[2], triage=_triage()),
        PreprocessResult(image=imgs[3], triage=_triage()),
    ]
    calls = {"i": 0}

    def fake_preprocess(img, config, **kw):
        r = results[calls["i"]]
        calls["i"] += 1
        return r

    monkeypatch.setattr(svc, "preprocess_page", fake_preprocess)
    blanks = {id(imgs[0]): False, id(imgs[1]): False, id(imgs[2]): False,
              id(imgs[3]): True}
    monkeypatch.setattr(svc, "is_blank_page", lambda gray, **kw: blanks[id(gray)])

    ocr_text = {
        id(imgs[0]): "APPLICATION FOR REGISTRATION\nForm A\nApplicant Name: ...",
        id(imgs[1]): "Some unrelated certificate text with no keywords",
        id(imgs[2]): "APPLICATION FOR REGISTRATION\nForm A\nApplicant Name: ...",
    }

    def fake_image_to_string(gray, lang=None):
        return ocr_text[id(gray)]

    monkeypatch.setattr(svc.pytesseract, "image_to_string", fake_image_to_string)
    return imgs


async def test_only_first_form_page_kept_as_form(tmp_path, patched_with_two_forms):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes")
    s3 = _FakeS3()

    manifest = await svc.upload_document(pdf, category="practitioner", s3=s3)

    p1, p2, p3, p4 = manifest.pages
    assert p1.page_type == "form"    # first application_form match wins
    assert p2.page_type == "other"   # no keywords
    assert p3.page_type == "other"   # demoted: second application_form match
    assert p4.page_type == "blank"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/nas/test_uploader_service.py::test_only_first_form_page_kept_as_form -v`

Expected: FAIL — `p3.page_type == "form"` (no demotion logic yet), so
`assert p3.page_type == "other"` fails.

- [ ] **Step 3: Implement the demotion post-process**

In `nas/uploader/service.py`, the per-page loop currently ends at line 97
(`logger.info("uploader.page", ...)`), and `manifest = Manifest(...)` starts
at line 99. Insert a post-process block between the loop and the `Manifest`
construction:

```python
    # "Earliest wins": only the first application_form-typed page carries the
    # handwritten identity block that needs VLM. Demote any later "form" pages
    # (continuation pages, or a second application form for a different
    # purpose) to "other" — Tesseract is sufficient for them, and Structure's
    # keyword typer still fine-types them from the Tesseract text.
    seen_form = False
    for i, page in enumerate(pages):
        if page.page_type != "form":
            continue
        if seen_form:
            pages[i] = page.model_copy(update={"page_type": "other"})
            logger.info("uploader.form_page_demoted", page_num=page.page_num)
        seen_form = True

    manifest = Manifest(
```

(The existing `manifest = Manifest(` line and everything after it stays
unchanged — this block is inserted immediately before it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/nas/test_uploader_service.py::test_only_first_form_page_kept_as_form -v`

Expected: PASS

- [ ] **Step 5: Run the full uploader test suite to confirm no regressions**

Run: `pytest tests/nas/test_uploader_service.py -v`

Expected: all tests PASS, including the existing
`test_form_page_detected_via_keyword_match` (single form page — no
demotion triggered, `seen_form` only flips once).

- [ ] **Step 6: Commit**

```bash
git add nas/uploader/service.py tests/nas/test_uploader_service.py
git commit -m "feat(nas): demote non-first application_form pages to other (A4)"
```

---

### Task 2: Update docs

**Files:**
- Modify: `documentation/session_log.md`
- Modify: `docs/superpowers/specs/2026-06-13-multi-form-page-vlm-selection-design.md` (mark implemented, if it has a status field — otherwise skip)

- [ ] **Step 1: Append a session_log.md entry**

Append (do not rewrite history) a new `##` section to
`documentation/session_log.md` summarizing: A4 implemented —
`nas/uploader/service.py::upload_document` now demotes any
`application_form`-typed page after the first to `"other"` ("earliest wins"),
so only the primary identity-bearing form page routes to VLM. New test
`test_only_first_form_page_kept_as_form` in
`tests/nas/test_uploader_service.py`. Note remaining backlog item: flush+rerun
(`make down-clean && make up && make init`) on all sample bundles is now the
next step (A1-A4 all done).

- [ ] **Step 2: Run full unit test suite**

Run: `make test` (or `pytest tests/ -m "not integration"`)

Expected: all green except the 1 pre-existing unrelated failure in
`tests/test_config_index.py::test_index_defaults` (env-var leak, documented
in prior session_log entries).

- [ ] **Step 3: Commit**

```bash
git add documentation/session_log.md
git commit -m "docs: A4 multi-form-page VLM selection done"
```
