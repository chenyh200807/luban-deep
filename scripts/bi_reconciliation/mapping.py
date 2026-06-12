"""18 个注册指标 → 三源取数声明。tolerance 按 trust_level：A=1% B=5% C=15%。

bi_api_path 已按 2026-06-12 test2 实拍 payload 回校（fixtures 见 tests/.../fixtures/）。
路径 DSL：`endpoint:dot.path` + 列表选择器 `list[key=value]`。
"""
from __future__ import annotations

from scripts.bi_reconciliation.types import MetricMapping

METRIC_MAPPINGS: tuple[MetricMapping, ...] = (
    MetricMapping(
        "effective_learning_members",
        bi_api_path="overview:north_star.value",
        business_kind="supabase_members",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "registered_members",
        bi_api_path="members:dashboard.total_count",
        business_kind="supabase_members",
        tolerance_pct=1.0,
    ),
    MetricMapping(
        "activated_members",
        bi_api_path="overview:growth_funnel.steps[id=activated_members].value",
        business_kind="supabase_members",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "active_learning_sessions",
        bi_api_path="overview:summary.total_sessions",
        langfuse_kind="daily_traces",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "success_turn_rate",
        bi_api_path="overview:summary.success_turn_rate",
        tolerance_pct=5.0,
        gap_note="Langfuse 侧无等价成功率口径（trace 级状态未回写），P1 仅记录 BI 值",
    ),
    MetricMapping(
        "avg_session_depth",
        bi_api_path="overview:summary.avg_session_depth",
        tolerance_pct=5.0,
        gap_note="Langfuse trace 深度口径与会话消息数口径不同，仅记录 BI 值",
    ),
    MetricMapping(
        "notebook_saves",
        bi_api_path="overview:summary.notebook_saves",
        business_kind="behavior_db",
        tolerance_pct=5.0,
    ),
    MetricMapping(
        "total_cost_usd",
        bi_api_path="cost:cards[label=总成本].value",
        langfuse_kind="daily_cost",
        tolerance_pct=15.0,
    ),
    MetricMapping(
        "renewal_risk_members",
        bi_api_path="members:dashboard.churn_risk_count",
        tolerance_pct=5.0,
        gap_note="风险集合为派生口径，业务库无独立真相，仅记录值",
    ),
    MetricMapping(
        "member_health_score",
        bi_api_path="overview:member_health.score.value",
        tolerance_pct=15.0,
        gap_note="复合评分无外部真相源，仅记录值与样本量",
    ),
    MetricMapping(
        "mastery_improvement",
        tolerance_pct=15.0,
        gap_note="2026-06-12 实拍：overview 仅暴露 teaching_effect.chapter_progress 逐章 mastery，无聚合提升值——注册指标未被 payload 实际承载",
    ),
    MetricMapping(
        "ai_quality_score",
        bi_api_path="overview:ai_quality.engineering_success_rate",
        tolerance_pct=5.0,
        gap_note="实拍 ai_quality.value=None，payload 实际承载 engineering_success_rate 代理字段——口径与注册定义不一致；Langfuse observations 总量与质量分不可比，不做等值对账",
    ),
    MetricMapping(
        "cost_per_effective_learning",
        bi_api_path="overview:unit_economics.value",
        tolerance_pct=15.0,
        gap_note="2026-06-12 实拍 value=None（cost=0.0198、有效学习者=10，本应可算）——已注册已展示但值未接线",
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
        tolerance_pct=1.0,
        gap_note="v1 显式 value=null（registry degraded_note 已声明），数值化列入 P3",
    ),
    # P2 注册表补全（F5 收口，2026-06-12）
    MetricMapping(
        "total_tokens",
        bi_api_path="cost:cards[label=总 Token].value",
        langfuse_kind="daily_observations",
        tolerance_pct=15.0,
        gap_note="Langfuse 侧 observations 数量与 token 数不可等值比，仅记录双方分量",
    ),
    MetricMapping(
        "today_cost_usd",
        tolerance_pct=15.0,
        gap_note="自然日窗口与对账 harness 的 N 天窗口不同口径，P1 不做等值比，由 P3 日粒度对账覆盖",
    ),
    MetricMapping(
        "avg_turn_cost_usd",
        bi_api_path="cost:cards[label=平均回合成本].value",
        tolerance_pct=15.0,
        gap_note="派生指标（ledger 成本 ÷ 会话回合数），无独立外部真相，仅记录",
    ),
    MetricMapping(
        "member_active_count",
        bi_api_path="members:dashboard.active_count",
        tolerance_pct=1.0,
        gap_note="canonical 口径在 member_console 聚合，外部暂不可独立复算（同 registered_members）",
    ),
    MetricMapping(
        "expiring_soon_members",
        bi_api_path="members:dashboard.expiring_soon_count",
        tolerance_pct=1.0,
        gap_note="到期窗口为 member_console 派生口径，仅记录",
    ),
)


def mapping_by_id(metric_id: str) -> MetricMapping:
    normalized = str(metric_id or "").strip()
    for m in METRIC_MAPPINGS:
        if m.metric_id == normalized:
            return m
    raise KeyError(f"Unknown metric mapping: {metric_id}")
