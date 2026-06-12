from __future__ import annotations

import json
from pathlib import Path

from scripts.bi_reconciliation.run import run_offline

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_offline_produces_report(tmp_path):
    out_dir = run_offline(
        fixtures_dir=FIXTURES,
        out_root=tmp_path,
        window_days=7,
        generated_at="2026-06-12T00:00:00Z",
    )
    from deeptutor.services.bi_metrics import BI_METRICS

    report = json.loads((out_dir / "reconciliation_report.json").read_text())
    assert report["summary"]["total"] == len(BI_METRICS)  # 全部注册指标都有 verdict
    assert (out_dir / "reconciliation_report.md").exists()
    dictionary = json.loads((out_dir / "metric_dictionary.json").read_text())
    assert len(dictionary) == len(BI_METRICS)


def test_run_offline_surfaces_known_findings(tmp_path):
    """实拍 fixtures 必须复现已知发现：成本覆盖缺口 + 注册表外标签。"""
    out_dir = run_offline(
        fixtures_dir=FIXTURES,
        out_root=tmp_path,
        window_days=7,
        generated_at="2026-06-12T00:00:00Z",
    )
    report = json.loads((out_dir / "reconciliation_report.json").read_text())
    by_id = {m["metric_id"]: m for m in report["metrics"]}
    # BI $0.0198 vs Langfuse $6.49 → coverage_gap
    assert by_id["total_cost_usd"]["verdict"] == "coverage_gap"
    assert by_id["total_cost_usd"]["diff_pct"] > 90
    # F5 收口后 2026-06-12 实拍 payload 不应再有注册表外标签
    assert report["unregistered_labels"] == []
