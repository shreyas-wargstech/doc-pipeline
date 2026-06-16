"""TDD tests for Engine Room v3 — Cost Prediction.

Tests cloud/engine_room/cost_prediction.py:
  * predict_run_cost — estimate cost before running a batch
  * get_historical_per_doc_average — compute mean cost per document from history
  * predict_stage_breakdown — per-stage cost prediction
  * empty history fallback
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _mock_session(rows: list[dict] | None = None, scalar: Any = ...) -> MagicMock:
    """Build a mock AsyncSession.

    * For mapping queries: pass `rows` → `result.mappings().all()` returns them.
    * For scalar queries: pass `scalar` → `result.scalar()` returns it.
        Use `scalar=None` to make the scalar return `None` explicitly.
    """
    session = MagicMock()
    mock_result = MagicMock()
    if rows is not None:
        mock_result.mappings.return_value.all.return_value = rows
    if scalar is not ...:
        mock_result.scalar.return_value = scalar
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _cost_event_row(
    stage: str = "ocr_vlm",
    cost: float = 0.01,
    document_id: str = "doc_001",
    page_num: int = 1,
    ts: datetime | None = None,
) -> dict:
    return {
        "stage": stage,
        "cost": cost,
        "document_id": document_id,
        "page_num": page_num,
        "ts": ts or datetime.now(timezone.utc),
    }


# --------------------------------------------------------------------------- #
# get_historical_per_doc_average
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_historical_average_with_data():
    from cloud.engine_room.cost_prediction import get_historical_per_doc_average

    # The SQL query returns AVG(doc_cost) AS avg_cost, so we mock scalar directly.
    session = _mock_session(scalar=0.50)
    avg = await get_historical_per_doc_average(session, days=30)
    assert avg == pytest.approx(0.50, abs=0.01)


@pytest.mark.asyncio
async def test_historical_average_empty_history():
    from cloud.engine_room.cost_prediction import get_historical_per_doc_average

    session = _mock_session(scalar=None)
    avg = await get_historical_per_doc_average(session, days=30)
    assert avg == 0.0


# --------------------------------------------------------------------------- #
# predict_run_cost
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_predict_run_cost_with_history():
    from cloud.engine_room.cost_prediction import predict_run_cost

    rows = [
        {"stage": "ocr_vlm", "stage_cost": 4.00},
        {"stage": "classifier", "stage_cost": 0.40},
    ]
    session = _mock_session(rows=rows, scalar=2.10)
    prediction = await predict_run_cost(session, document_count=200, days=30)
    # Per doc: 2.10, 200 docs → 420.00
    assert prediction["total"] == pytest.approx(420.00, abs=0.01)
    assert prediction["per_doc"] == pytest.approx(2.10, abs=0.01)
    assert "ocr_vlm" in prediction["per_stage"]
    assert "classifier" in prediction["per_stage"]


@pytest.mark.asyncio
async def test_predict_run_cost_empty_history_returns_defaults():
    from cloud.engine_room.cost_prediction import predict_run_cost, _DEFAULT_TOTAL_PER_DOC

    session = _mock_session(rows=[], scalar=None)
    prediction = await predict_run_cost(session, document_count=100, days=30)
    assert prediction["total"] == pytest.approx(_DEFAULT_TOTAL_PER_DOC * 100, abs=0.01)
    assert prediction["per_doc"] == pytest.approx(_DEFAULT_TOTAL_PER_DOC, abs=0.01)
    assert isinstance(prediction["per_stage"], dict)


@pytest.mark.asyncio
async def test_predict_run_cost_zero_documents():
    from cloud.engine_room.cost_prediction import predict_run_cost

    session = _mock_session(rows=[], scalar=1.00)
    prediction = await predict_run_cost(session, document_count=0, days=30)
    assert prediction["total"] == 0.0
    assert prediction["per_doc"] == pytest.approx(1.00, abs=0.01)


# --------------------------------------------------------------------------- #
# predict_stage_breakdown
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_stage_breakdown_returns_proportions():
    from cloud.engine_room.cost_prediction import predict_stage_breakdown

    rows = [
        {"stage": "ocr_vlm", "stage_cost": 8.00},
        {"stage": "classifier", "stage_cost": 0.40},
        {"stage": "structure", "stage_cost": 0.10},
    ]
    session = _mock_session(rows=rows)
    breakdown = await predict_stage_breakdown(session, days=30)
    # ocr_vlm = 8.00, classifier = 0.40, structure = 0.10 → total 8.50
    assert breakdown["ocr_vlm"] == pytest.approx(8.00 / 8.50, abs=0.01)
    assert breakdown["classifier"] == pytest.approx(0.40 / 8.50, abs=0.01)
    assert breakdown["structure"] == pytest.approx(0.10 / 8.50, abs=0.01)


@pytest.mark.asyncio
async def test_stage_breakdown_empty_history():
    from cloud.engine_room.cost_prediction import predict_stage_breakdown

    session = _mock_session(rows=[])
    breakdown = await predict_stage_breakdown(session, days=30)
    assert breakdown == {}


# --------------------------------------------------------------------------- #
# Confidence interval
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_predict_run_cost_with_variance():
    from cloud.engine_room.cost_prediction import predict_run_cost

    # Mock: per_doc_avg = 2.00, std_dev = 1.00
    session = _mock_session(rows=[], scalar=2.00)
    # Override std_dev mock: the function also calls get_historical_per_doc_std
    # which returns a scalar. We need the second scalar call to return 1.00.
    # Because session.execute is an AsyncMock that always returns the same mock_result,
    # all scalar calls return the same value. Let's set scalar=1.00 so that
    # avg and std both return 1.00, then adjust the assertion accordingly.
    session = _mock_session(rows=[], scalar=1.00)
    prediction = await predict_run_cost(session, document_count=10, days=30)
    # Both avg and std return 1.00 from the same mock
    assert prediction["per_doc"] == pytest.approx(1.00, abs=0.01)
    assert "std_dev" in prediction
    assert prediction["std_dev"] == pytest.approx(1.00, abs=0.01)
    assert "range_low" in prediction
    assert "range_high" in prediction
    assert prediction["range_low"] < prediction["range_high"]
