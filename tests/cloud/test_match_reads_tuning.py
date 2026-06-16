import pytest

from cloud.match.tuning import load_match_thresholds
from cloud.match.models import FUZZY_MATCH_HIGH, FUZZY_REVIEW_LOW


@pytest.mark.asyncio
async def test_defaults_when_no_rows():
    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return []
            return M()

    class FakeSession:
        async def execute(self, *a, **k):
            return FakeResult()

    th = await load_match_thresholds(FakeSession())
    assert th["fuzzy_match_high"] == FUZZY_MATCH_HIGH
    assert th["fuzzy_review_low"] == FUZZY_REVIEW_LOW


@pytest.mark.asyncio
async def test_override_from_tuning():
    rows = [{"name": "fuzzy_match_high", "value": "85"}]

    class FakeResult:
        def mappings(self):
            class M:
                def all(self_inner):
                    return rows
            return M()

    class FakeSession:
        async def execute(self, *a, **k):
            return FakeResult()

    th = await load_match_thresholds(FakeSession())
    assert th["fuzzy_match_high"] == 85.0
    assert th["fuzzy_review_low"] == FUZZY_REVIEW_LOW  # untouched default
