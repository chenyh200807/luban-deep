"""对账引擎：纯函数，三源读数 → 五类 verdict。

attribution_error 由人工在报告复核时从 definition_mismatch 升级标注——
自动规则无法区分口径分歧与归因错误，引擎不假装能。
"""
from __future__ import annotations

from scripts.bi_reconciliation.types import (
    SOURCE_BI_API,
    SOURCE_BUSINESS,
    VERDICT_CONSISTENT,
    VERDICT_COVERAGE_GAP,
    VERDICT_DEFINITION_MISMATCH,
    VERDICT_ESTIMATE_CONTAMINATION,
    VERDICT_MISSING_SOURCE,
    MetricMapping,
    MetricVerdict,
    SourceReading,
)

# 真相源优先序：业务库（财务/会员级权威）> Langfuse（AI 观测权威）
_TRUTH_PRIORITY = (SOURCE_BUSINESS, "langfuse")


def reconcile_metric(mapping: MetricMapping, readings: list[SourceReading]) -> MetricVerdict:
    valid = [r for r in readings if r.value is not None]
    bi = next((r for r in valid if r.source == SOURCE_BI_API), None)
    truth = next(
        (
            r
            for source in _TRUTH_PRIORITY
            for r in valid
            if r.source == source
        ),
        None,
    )
    if bi is None or truth is None:
        missing = sorted({r.source for r in readings if r.value is None}) or ["truth_source"]
        return MetricVerdict(
            mapping.metric_id,
            VERDICT_MISSING_SOURCE,
            tuple(readings),
            None,
            f"缺有效读数: {','.join(missing)}",
        )
    base = max(abs(truth.value), 1e-9)
    diff_pct = abs(bi.value - truth.value) / base * 100
    if diff_pct <= mapping.tolerance_pct:
        return MetricVerdict(mapping.metric_id, VERDICT_CONSISTENT, tuple(readings), diff_pct, "一致")
    mix = bi.meta.get("usage_source_mix") or {}
    if float(mix.get("estimated_ratio") or 0) > 0.1:
        return MetricVerdict(
            mapping.metric_id,
            VERDICT_ESTIMATE_CONTAMINATION,
            tuple(readings),
            diff_pct,
            f"BI 值含 {float(mix['estimated_ratio']):.0%} 估算分量且超容忍度",
        )
    if bi.value < truth.value:
        return MetricVerdict(
            mapping.metric_id,
            VERDICT_COVERAGE_GAP,
            tuple(readings),
            diff_pct,
            f"BI({bi.value:g}) 低于真相源 {truth.source}({truth.value:g})——疑似采集缺口",
        )
    return MetricVerdict(
        mapping.metric_id,
        VERDICT_DEFINITION_MISMATCH,
        tuple(readings),
        diff_pct,
        f"BI({bi.value:g}) 高于真相源 {truth.source}({truth.value:g})——疑似口径分歧或归因错误",
    )
