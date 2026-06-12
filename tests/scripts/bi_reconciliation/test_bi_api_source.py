from __future__ import annotations

import json
from pathlib import Path

from scripts.bi_reconciliation.bi_api_source import (
    extract_bi_readings,
    find_unregistered_labels,
)
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS

FIXTURES = Path(__file__).parent / "fixtures"


def _payloads() -> dict:
    return {
        "overview": json.loads((FIXTURES / "bi_overview.json").read_text()),
        "cost": json.loads((FIXTURES / "bi_cost.json").read_text()),
        "members": json.loads((FIXTURES / "bi_members.json").read_text()),
    }


def test_extract_returns_reading_for_every_mapped_metric():
    readings = extract_bi_readings(_payloads(), window_days=7)
    got_ids = {r.metric_id for r in readings}
    expected = {m.metric_id for m in METRIC_MAPPINGS if m.bi_api_path}
    assert got_ids == expected
    for r in readings:
        assert r.source == "bi_api"
        if r.value is None:
            assert "reason" in r.meta, r.metric_id


def test_known_real_values_resolve_from_fixture():
    """锚定 2026-06-12 实拍值——extractor 路径解析正确性的金标。"""
    readings = {r.metric_id: r for r in extract_bi_readings(_payloads(), window_days=7)}
    assert readings["effective_learning_members"].value == 10
    assert readings["registered_members"].value == 93
    assert readings["activated_members"].value == 10
    assert readings["active_learning_sessions"].value == 857
    assert readings["total_cost_usd"].value == 0.0198
    # 实拍取证：已注册已展示但 value 键缺失——未接线（P1 finding）
    assert readings["cost_per_effective_learning"].value is None
    assert readings["cost_per_effective_learning"].meta["reason"] == "path_not_found:value"


def test_total_cost_cross_check_records_overview_summary():
    """overview.summary.total_cost_usd 与 cost 端点的内部互拍记录进 meta。"""
    readings = {r.metric_id: r for r in extract_bi_readings(_payloads(), window_days=7)}
    meta = readings["total_cost_usd"].meta
    assert "overview_summary_total_cost_usd" in meta
    # 2026-06-12 实拍：overview 报 0.0，cost 端点报 0.0198——内部自相矛盾的证据
    assert meta["overview_summary_total_cost_usd"] == 0.0


def test_unregistered_kpi_labels_are_reported():
    unknown = find_unregistered_labels(_payloads())
    assert isinstance(unknown, list)
    # 实拍 payload 中 boss_workbench kpi「今日成本」不在注册表 label/alias 中
    assert "今日成本" in unknown
