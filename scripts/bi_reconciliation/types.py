from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCE_BI_API = "bi_api"
SOURCE_LANGFUSE = "langfuse"
SOURCE_BUSINESS = "business"

VERDICT_CONSISTENT = "consistent"  # 一致
VERDICT_ESTIMATE_CONTAMINATION = "estimate_contamination"  # 估算污染
VERDICT_COVERAGE_GAP = "coverage_gap"  # 覆盖缺口
VERDICT_ATTRIBUTION_ERROR = "attribution_error"  # 归因错误（人工复核升级）
VERDICT_DEFINITION_MISMATCH = "definition_mismatch"  # 口径分歧
VERDICT_MISSING_SOURCE = "missing_source"  # 某源无法取数（声明性缺口）


@dataclass(frozen=True, slots=True)
class SourceReading:
    metric_id: str
    source: str  # SOURCE_*
    value: float | None  # None = 取数失败/不适用
    window_days: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricMapping:
    metric_id: str
    bi_api_path: str = ""  # 形如 "overview:cards[label=...].value"
    langfuse_kind: str = ""  # "" | "daily_cost" | "daily_traces" | "daily_observations"
    business_kind: str = ""  # "" | "supabase_members" | "behavior_db"
    tolerance_pct: float = 5.0  # 相对偏差容忍度（按 trust_level: A=1 B=5 C=15）
    gap_note: str = ""  # 显式声明的缺源原因


@dataclass(frozen=True, slots=True)
class MetricVerdict:
    metric_id: str
    verdict: str  # VERDICT_*
    readings: tuple[SourceReading, ...]
    diff_pct: float | None
    detail: str
