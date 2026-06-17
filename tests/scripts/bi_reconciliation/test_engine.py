from __future__ import annotations

from scripts.bi_reconciliation.engine import reconcile_metric
from scripts.bi_reconciliation.types import (
    SOURCE_BI_API,
    SOURCE_BUSINESS,
    SOURCE_LANGFUSE,
    VERDICT_CONSISTENT,
    VERDICT_COVERAGE_GAP,
    VERDICT_DEFINITION_MISMATCH,
    VERDICT_ESTIMATE_CONTAMINATION,
    VERDICT_MISSING_SOURCE,
    MetricMapping,
    SourceReading,
)


def _r(source: str, value: float | None, **meta) -> SourceReading:
    return SourceReading("m", source, value, 7, meta)


M = MetricMapping("m", bi_api_path="overview:x", langfuse_kind="daily_cost", tolerance_pct=5.0)


def test_consistent_within_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 100.0), _r(SOURCE_LANGFUSE, 103.0)])
    assert v.verdict == VERDICT_CONSISTENT
    assert v.diff_pct is not None and v.diff_pct < 5.0


def test_estimate_contamination_when_meta_says_estimated():
    v = reconcile_metric(
        M,
        [
            _r(SOURCE_BI_API, 100.0, usage_source_mix={"estimated_ratio": 0.4}),
            _r(SOURCE_LANGFUSE, 130.0),
        ],
    )
    assert v.verdict == VERDICT_ESTIMATE_CONTAMINATION


def test_coverage_gap_when_bi_lower_beyond_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 50.0), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_COVERAGE_GAP


def test_definition_mismatch_when_bi_higher_beyond_tolerance():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 200.0), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_DEFINITION_MISMATCH


def test_missing_source_when_only_one_reading():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 100.0)])
    assert v.verdict == VERDICT_MISSING_SOURCE


def test_none_values_treated_as_missing():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, None), _r(SOURCE_LANGFUSE, 100.0)])
    assert v.verdict == VERDICT_MISSING_SOURCE
    assert "bi_api" in v.detail


def test_truth_source_priority_business_over_langfuse_when_both_present():
    """同时有 business 与 langfuse 真相源时按 mapping 声明序取首个有效。"""
    v = reconcile_metric(
        M,
        [
            _r(SOURCE_BI_API, 100.0),
            _r(SOURCE_BUSINESS, 100.0),
            _r(SOURCE_LANGFUSE, 999.0),
        ],
    )
    assert v.verdict == VERDICT_CONSISTENT
    assert v.diff_pct == 0.0


def test_zero_truth_value_does_not_divide_by_zero():
    v = reconcile_metric(M, [_r(SOURCE_BI_API, 5.0), _r(SOURCE_LANGFUSE, 0.0)])
    assert v.verdict == VERDICT_DEFINITION_MISMATCH
    assert v.diff_pct is not None
