"""18 个注册指标 → 三源取数声明。tolerance 按 trust_level：A=1% B=5% C=15%。

bi_api_path 初值为锚点，Task 2 录制真实 payload 后必须回校为真实字段路径。
"""
from __future__ import annotations

from scripts.bi_reconciliation.types import MetricMapping

METRIC_MAPPINGS: tuple[MetricMapping, ...] = (
    MetricMapping(
        "effective_learning_members",
        bi_api_path="overview:north_star",
        business_kind="supabase_members",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "registered_members",
        bi_api_path="overview:registered",
        business_kind="supabase_members",
        tolerance_pct=1.0,
    ),
    MetricMapping(
        "activated_members",
        bi_api_path="overview:activated",
        business_kind="supabase_members",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "active_learning_sessions",
        bi_api_path="overview:sessions",
        langfuse_kind="daily_traces",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "success_turn_rate",
        bi_api_path="overview:success_rate",
        langfuse_kind="daily_traces",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "avg_session_depth",
        bi_api_path="overview:depth",
        tolerance_pct=5.0,
        gap_note="Langfuse trace 深度口径与会话消息数口径不同，仅记录 BI 值",
    ),
    MetricMapping(
        "notebook_saves",
        bi_api_path="overview:notebook",
        business_kind="behavior_db",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "total_cost_usd",
        bi_api_path="cost:total",
        langfuse_kind="daily_cost",
        tolerance_pct=15.0,
    ),
    MetricMapping(
        "renewal_risk_members",
        bi_api_path="members:renewal_risk",
        tolerance_pct=5.0,
        gap_note="风险集合为派生口径，业务库无独立真相，仅记录值",
    ),
    MetricMapping(
        "member_health_score",
        bi_api_path="overview:member_health",
        tolerance_pct=15.0,
        gap_note="复合评分无外部真相源，仅记录值与样本量",
    ),
    MetricMapping(
        "mastery_improvement",
        bi_api_path="overview:mastery",
        tolerance_pct=15.0,
        gap_note="learner_state read model 为唯一源，仅记录",
    ),
    MetricMapping(
        "ai_quality_score",
        bi_api_path="overview:ai_quality",
        langfuse_kind="daily_observations",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "cost_per_effective_learning",
        bi_api_path="cost:per_learning",
        langfuse_kind="daily_cost",
        tolerance_pct=15.0,
    ),
    MetricMapping(
        "behavior.module.open_count",
        business_kind="behavior_db",
        gap_note="overview payload 不直接暴露，经 member-ops 聚合；P1 先 DB 侧单源记录",
    ),
    MetricMapping(
        "behavior.learning_report.section_view_count",
        business_kind="behavior_db",
        gap_note="overview payload 不直接暴露；P1 先 DB 侧单源记录",
    ),
    MetricMapping(
        "behavior.funnel.report_to_training",
        business_kind="behavior_db",
        gap_note="派生漏斗，P1 先 DB 侧记录分量",
    ),
    MetricMapping(
        "behavior.member_ops.report_high_no_action",
        business_kind="behavior_db",
        gap_note="运营队列口径，P1 先 DB 侧记录分量",
    ),
    MetricMapping(
        "data_trust_score",
        bi_api_path="overview:data_trust",
        tolerance_pct=1.0,
        gap_note="自反指标，无外部真相，仅记录",
    ),
)


def mapping_by_id(metric_id: str) -> MetricMapping:
    normalized = str(metric_id or "").strip()
    for m in METRIC_MAPPINGS:
        if m.metric_id == normalized:
            return m
    raise KeyError(f"Unknown metric mapping: {metric_id}")
