import pytest

from cloud.identity.intelligence import generate_consistency_report


class _Page:
    def __init__(self, sj):
        self.structured_json = sj


@pytest.mark.asyncio
async def test_consistent_names_score_high():
    pages = [
        _Page({"extracted_name": "Ashish Patil"}),
        _Page({"extracted_name": "Ashish Ramesh Patil"}),
    ]
    report = await generate_consistency_report("doc-1", pages)
    assert report["name_score"] >= 90.0
    assert 0 <= report["overall_score"] <= 100


@pytest.mark.asyncio
async def test_mismatched_names_score_low():
    pages = [
        _Page({"extracted_name": "Ashish Patil"}),
        _Page({"extracted_name": "Rahul Sharma"}),
    ]
    report = await generate_consistency_report("doc-1", pages)
    assert report["name_score"] < 60.0
