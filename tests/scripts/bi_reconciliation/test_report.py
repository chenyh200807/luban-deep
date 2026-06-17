from __future__ import annotations

from scripts.bi_reconciliation.report import (
    build_metric_dictionary,
    build_report,
    render_markdown,
)
from scripts.bi_reconciliation.types import MetricVerdict, SourceReading


def _verdict(mid: str, verdict: str, diff: float | None) -> MetricVerdict:
    return MetricVerdict(mid, verdict, (SourceReading(mid, "bi_api", 1.0, 7),), diff, "x")


def test_report_json_shape_and_summary():
    vs = [_verdict("a", "consistent", 1.0), _verdict("b", "coverage_gap", 50.0)]
    rep = build_report(
        vs, window_days=7, generated_at="2026-06-12T00:00:00Z", unregistered_labels=["神秘KPI"]
    )
    assert rep["schema_version"] == 1
    assert rep["summary"]["total"] == 2
    assert rep["summary"]["by_verdict"]["coverage_gap"] == 1
    assert rep["unregistered_labels"] == ["神秘KPI"]
    assert rep["metrics"][0]["metric_id"] == "a"
    assert rep["metrics"][0]["readings"][0]["source"] == "bi_api"


def test_markdown_rendering_groups_by_verdict():
    vs = [_verdict("a", "consistent", 1.0), _verdict("b", "coverage_gap", 50.0)]
    rep = build_report(vs, window_days=7, generated_at="2026-06-12T00:00:00Z",
                       unregistered_labels=["神秘KPI"])
    md = render_markdown(rep)
    assert "coverage_gap" in md
    assert "神秘KPI" in md
    assert "| b |" in md


def test_metric_dictionary_includes_registry_and_mapping_fields():
    d = build_metric_dictionary()
    from deeptutor.services.bi_metrics import BI_METRICS

    assert len(d) == len(BI_METRICS)
    sample = next(x for x in d if x["metric_id"] == "total_cost_usd")
    assert sample["trust_level"] == "B"
    assert sample["mapping"]["langfuse_kind"] == "daily_cost"
    assert sample["definition"]
