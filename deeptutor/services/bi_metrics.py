from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BIMetricDefinition:
    metric_id: str
    label: str
    group: str
    definition: str
    authority: str
    trust_level: str
    owner: str
    drilldown: str
    display_hint: str = ""
    # Round 3 D: surface refresh cadence + known degradation note so the
    # frontend KPI tooltip (plan §3.6) can be generated from a single backend
    # truth instead of a hand-maintained TypeScript mirror.
    refresh_cadence: str = "近实时"
    degraded_note: str = ""
    # Alternate human-readable labels emitted by overview cards (Chinese
    # variants). Used by the frontend label→metric_id resolver when payloads
    # only carry label text.
    label_aliases: tuple[str, ...] = field(default_factory=tuple)


BI_METRICS: tuple[BIMetricDefinition, ...] = (
    BIMetricDefinition(
        metric_id="effective_learning_members",
        label="有效学习成功会员数",
        group="north_star",
        definition="窗口内有真实手机号会员身份，并完成至少一次有效学习会话或学习成果的会员数。",
        authority="bi_service",
        trust_level="B",
        owner="boss",
        drilldown="member_ops",
        display_hint="北极星指标",
        refresh_cadence="近实时 (overview API)",
        degraded_note="session store / member_console 任一降级时数值偏低；overview banner 同步标红。",
        label_aliases=("有效学习成功会员",),
    ),
    BIMetricDefinition(
        metric_id="registered_members",
        label="真实注册会员数",
        group="growth",
        definition="通过会员系统 canonical member 口径过滤后的真实手机号会员数，不包含测试、探针和演练账号。",
        authority="member_console",
        trust_level="A",
        owner="ops",
        drilldown="member_ops",
        refresh_cadence="近实时 (Supabase REST)",
        label_aliases=("真实注册会员",),
    ),
    BIMetricDefinition(
        metric_id="activated_members",
        label="激活会员数",
        group="growth",
        definition="窗口内至少有一次真实学习会话的注册会员数。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="member_ops",
        refresh_cadence="近实时 (聚合 session_store)",
        degraded_note="session_store 同步延迟时窗口尾部样本偏少。",
        label_aliases=("活跃学习者",),
    ),
    BIMetricDefinition(
        metric_id="active_learning_sessions",
        label="活跃学习会话",
        group="overview",
        definition="窗口内更新过的会话数。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="member_ops",
        refresh_cadence="近实时",
        degraded_note="TutorBot 回写降级时仅基于客户端 events，可能漏会话。",
        label_aliases=("活跃学习会话数",),
    ),
    BIMetricDefinition(
        metric_id="success_turn_rate",
        label="回合成功率",
        group="ai_quality",
        definition="成功完成的回合数占总回合数的比例。",
        authority="bi_service",
        trust_level="B",
        owner="quality",
        drilldown="feedback",
        refresh_cadence="近实时",
        degraded_note="Langfuse 评估延迟时分子滞后，分母先到，比例偏低。",
    ),
    BIMetricDefinition(
        metric_id="avg_session_depth",
        label="平均会话深度",
        group="overview",
        definition="每个会话的平均消息数。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="overview",
        refresh_cadence="近实时",
    ),
    BIMetricDefinition(
        metric_id="notebook_saves",
        label="Notebook 保存",
        group="learning_evidence",
        definition="问题笔记沉淀量。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="overview",
        refresh_cadence="近实时",
        label_aliases=("笔记沉淀",),
    ),
    BIMetricDefinition(
        metric_id="total_cost_usd",
        label="总成本",
        group="unit_economics",
        definition="窗口内估算总 AI 成本 (USD)。Langfuse 估算，未与账单对账。",
        authority="observability.cost_estimator",
        trust_level="C",
        owner="platform",
        drilldown="ops",
        refresh_cadence="每 5 分钟批 (Langfuse pull)",
        degraded_note="估算值与真实账单存在 ± 15% 偏差；不可作为财务结算依据。",
        label_aliases=("近 24h LLM 成本", "近 7d 总成本"),
    ),
    BIMetricDefinition(
        metric_id="renewal_risk_members",
        label="续费风险会员数",
        group="member_ops",
        definition="即将到期、沉默、高风险或高成本低效果的会员集合。",
        authority="member_console",
        trust_level="B",
        owner="ops",
        drilldown="member_ops",
        refresh_cadence="每 5 分钟 (member_console 聚合)",
        degraded_note="学习证据未同步时风险评分偏低。",
        label_aliases=("续费风险会员",),
    ),
    BIMetricDefinition(
        metric_id="member_health_score",
        label="会员健康评分",
        group="member_health",
        definition="由学习行为、会员价值、学习效果、AI 体验和运营关系组成的透明风险评分；样本不足时只展示风险标签和原因。",
        authority="bi_service",
        trust_level="C",
        owner="ops",
        drilldown="member_ops",
        refresh_cadence="每 15 分钟",
        degraded_note="样本量 < 阈值时仅展示风险标签和原因，不展示分值。",
        label_aliases=("会员健康",),
    ),
    BIMetricDefinition(
        metric_id="mastery_improvement",
        label="章节掌握度提升",
        group="teaching_effect",
        definition="基于 member learner state 中章节掌握度和弱点闭环信号计算的学习效果指标。",
        authority="learner_state",
        trust_level="C",
        owner="teaching",
        drilldown="teaching_effect",
        refresh_cadence="每 15 分钟",
        degraded_note="learner_state read model 同步延迟时窗口尾部掌握度偏低；样本量 < 10 时不展示。",
    ),
    BIMetricDefinition(
        metric_id="ai_quality_score",
        label="AI 教学质量分",
        group="ai_quality",
        definition="由回合成功率、反馈、追问、工具/RAG 信号和异常样本共同形成的质量摘要。",
        authority="bi_service",
        trust_level="B",
        owner="quality",
        drilldown="feedback",
        refresh_cadence="近实时",
        degraded_note="Langfuse / 用户反馈源任一缺数据时切到 placeholder，不参与排名。",
        label_aliases=("AI 质量",),
    ),
    BIMetricDefinition(
        metric_id="cost_per_effective_learning",
        label="单有效学习成本",
        group="unit_economics",
        definition="窗口总 AI 成本除以有效学习成功会员数；收入未接入时只展示成本侧。",
        authority="bi_service",
        trust_level="B",
        owner="boss",
        drilldown="ops",
        refresh_cadence="每 5 分钟",
        degraded_note="成本估算 C 级时此指标也降级到 C 级。",
        label_aliases=("单次学习成本",),
    ),
    BIMetricDefinition(
        metric_id="behavior.module.open_count",
        label="模块打开次数",
        group="product_behavior",
        definition="窗口内用户进入学习产品模块的次数，来自 product_behavior_events indexed raw read model。",
        authority="product_behavior_store",
        trust_level="B",
        owner="product",
        drilldown="member_ops",
        refresh_cadence="近实时 indexed raw read",
        degraded_note="visit_id、release_id 或 section visibility 缺失时降级为 B/C。",
    ),
    BIMetricDefinition(
        metric_id="behavior.learning_report.section_view_count",
        label="学情 section 浏览次数",
        group="product_behavior",
        definition="窗口内学情页 section 进入视口或 fallback 渲染曝光次数。",
        authority="product_behavior_store",
        trust_level="B",
        owner="product",
        drilldown="member_ops",
        refresh_cadence="近实时 indexed raw read",
        degraded_note="小程序/yousen 曝光口径未完成三端一致 smoke 前保持 B 级。",
    ),
    BIMetricDefinition(
        metric_id="behavior.funnel.report_to_training",
        label="学情到训练转化",
        group="product_behavior",
        definition="学情浏览后进入训练的用户或 visit 占比。",
        authority="product_behavior_store",
        trust_level="B",
        owner="product",
        drilldown="member_ops",
        refresh_cadence="近实时 indexed raw read",
        degraded_note="缺 visit_id 时不进入 A 级漏斗。",
    ),
    BIMetricDefinition(
        metric_id="behavior.member_ops.report_high_no_action",
        label="学情高频无行动",
        group="product_behavior",
        definition="7 天学情打开不少于 3 次且训练/复测开始为 0 的会员队列。",
        authority="product_behavior_store",
        trust_level="B",
        owner="ops",
        drilldown="member_ops",
        refresh_cadence="近实时 indexed raw read",
        degraded_note="低可信 cohort 只允许人工参考，不进入自动运营队列。",
    ),
    BIMetricDefinition(
        metric_id="data_trust_score",
        label="数据可信度分",
        group="data_trust",
        definition="基于接口降级、数据源缺口、指标口径完整度和更新时间形成的可信度摘要。",
        authority="bi_service",
        trust_level="A",
        owner="engineering",
        drilldown="ops",
        refresh_cadence="近实时",
        label_aliases=("数据可信",),
    ),
)


def metric_by_id(metric_id: str) -> BIMetricDefinition:
    normalized = str(metric_id or "").strip()
    for metric in BI_METRICS:
        if metric.metric_id == normalized:
            return metric
    raise KeyError(f"Unknown BI metric: {metric_id}")
