import pytest

from cloud.self_healing import identity_search


class _Page:
    def __init__(self, page_num, page_type):
        self.page_num = page_num
        self.page_type = page_type


@pytest.mark.asyncio
async def test_finds_hidden_identity_page():
    pages = [_Page(1, "other"), _Page(2, "marksheet"), _Page(3, "other")]

    async def fake_classify(page):
        return "application_form" if page.page_num == 3 else "other"

    found = await identity_search.find_hidden_identity_page(pages, classify=fake_classify)
    assert found is not None and found.page_num == 3


@pytest.mark.asyncio
async def test_no_hidden_identity_page_returns_none():
    pages = [_Page(1, "other"), _Page(2, "marksheet")]

    async def fake_classify(page):
        return "other"

    found = await identity_search.find_hidden_identity_page(pages, classify=fake_classify)
    assert found is None
