"""差异报告（JSON + Markdown）与指标字典生成。纯函数，时间由调用方注入。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from deeptutor.services.bi_metrics import BI_METRICS
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS, mapping_by_id
from scripts.bi_reconciliation.types import MetricVerdict

_VERDICT_ORDER = (
    "coverage_gap",
    "estimate_contamination",
    "definition_mismatch",
    "attribution_error",
    "missing_source",
    "consistent",
)

_VERDICT_LABELS = {
    "consistent": "一致",
    "estimate_contamination": "估算污染",
    "coverage_gap": "覆盖缺口",
    "attribution_error": "归因错误",
    "definition_mismatch": "口径分歧",
    "missing_source": "缺源",
}


def build_report(
    verdicts: list[MetricVerdict],
    *,
    window_days: int,
    generated_at: str,
    unregistered_labels: list[str],
) -> dict[str, Any]:
    by_verdict: dict[str, int] = {}
    for v in verdicts:
        by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "window_days": window_days,
        "summary": {"total": len(verdicts), "by_verdict": by_verdict},
        "metrics": [
            {
                "metric_id": v.metric_id,
                "verdict": v.verdict,
                "diff_pct": v.diff_pct,
                "detail": v.detail,
                "readings": [asdict(r) for r in v.readings],
            }
            for v in verdicts
        ],
        "unregistered_labels": list(unregistered_labels),
    }


def _reading_value(metric: dict[str, Any], source: str) -> str:
    for r in metric["readings"]:
        if r["source"] == source:
            return "—" if r["value"] is None else f"{r['value']:g}"
    return "·"


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        "# BI 三源对账差异报告",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 窗口: {report['window_days']} 天",
        f"- 指标总数: {report['summary']['total']}",
        "",
        "## Verdict 汇总",
        "",
    ]
    for verdict, count in sorted(report["summary"]["by_verdict"].items()):
        lines.append(f"- **{verdict}**（{_VERDICT_LABELS.get(verdict, verdict)}）: {count}")
    for verdict in _VERDICT_ORDER:
        group = [m for m in report["metrics"] if m["verdict"] == verdict]
        if not group:
            continue
        lines += [
            "",
            f"## {verdict}（{_VERDICT_LABELS.get(verdict, verdict)}）",
            "",
            "| 指标 | BI 值 | Langfuse | 业务库 | diff% | 说明 | 人工复核 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for m in group:
            diff = "—" if m["diff_pct"] is None else f"{m['diff_pct']:.1f}%"
            lines.append(
                f"| {m['metric_id']} | {_reading_value(m, 'bi_api')}"
                f" | {_reading_value(m, 'langfuse')} | {_reading_value(m, 'business')}"
                f" | {diff} | {m['detail']} | |"
            )
    if report["unregistered_labels"]:
        lines += [
            "",
            "## 注册表外 KPI 标签（P2 收口清单）",
            "",
        ]
        lines += [f"- {label}" for label in report["unregistered_labels"]]
    lines.append("")
    return "\n".join(lines)


def build_metric_dictionary() -> list[dict[str, Any]]:
    """指标字典 = 注册表全字段 + 对账映射全字段（单一权威联合视图）。"""
    out: list[dict[str, Any]] = []
    for metric in BI_METRICS:
        entry: dict[str, Any] = asdict(metric)
        entry["label_aliases"] = list(metric.label_aliases)
        entry["mapping"] = asdict(mapping_by_id(metric.metric_id))
        out.append(entry)
    assert len(out) == len(METRIC_MAPPINGS)
    return out
