from __future__ import annotations

import json
from pathlib import Path

from scripts.bi_reconciliation.langfuse_source import readings_from_daily_metrics

FIXTURES = Path(__file__).parent / "fixtures"


def _daily() -> dict:
    return json.loads((FIXTURES / "langfuse_daily.json").read_text())


def test_daily_cost_aggregation_matches_fixture_sum():
    daily = _daily()
    readings = {r.metric_id: r for r in readings_from_daily_metrics(daily, window_days=7)}
    cost = readings["total_cost_usd"]
    assert cost.source == "langfuse"
    expected = sum(float(d.get("totalCost") or 0) for d in daily["data"])
    assert cost.value is not None
    assert abs(cost.value - expected) < 1e-9
    # 2026-06-12 实拍锚定值：7 天 Langfuse 真实成本 ~6.49 USD
    assert 6.0 < cost.value < 7.0
    assert cost.meta["days"] == 7


def test_trace_counts():
    readings = {r.metric_id: r for r in readings_from_daily_metrics(_daily(), window_days=7)}
    assert readings["active_learning_sessions"].value == 898.0  # daily_traces


def test_empty_payload_yields_none_values():
    readings = readings_from_daily_metrics({"data": []}, window_days=7)
    assert readings, "映射了 langfuse_kind 的指标应仍有读数"
    for r in readings:
        assert r.value is None
        assert r.meta["reason"] == "no_daily_rows"
