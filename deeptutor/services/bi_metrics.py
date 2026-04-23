from __future__ import annotations

from dataclasses import dataclass


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
    ),
    BIMetricDefinition(
        metric_id="activated_members",
        label="激活会员数",
        group="growth",
        definition="窗口内至少有一次真实学习会话的注册会员数。",
        authority="bi_service",
        trust_level="B",
        owner="product",
        drilldown="student_360",
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
    ),
    BIMetricDefinition(
        metric_id="member_health_score",
        label="会员健康评分",
        group="member_health",
        definition="由学习行为、会员价值、学习效果、AI 体验和运营关系组成的透明风险评分；样本不足时只展示风险标签和原因。",
        authority="bi_service",
        trust_level="C",
        owner="ops",
        drilldown="student_360",
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
    ),
    BIMetricDefinition(
        metric_id="ai_quality_score",
        label="AI 教学质量分",
        group="ai_quality",
        definition="由回合成功率、反馈、追问、工具/RAG 信号和异常样本共同形成的质量摘要。",
        authority="bi_service",
        trust_level="B",
        owner="engineering",
        drilldown="ai_quality",
    ),
    BIMetricDefinition(
        metric_id="cost_per_effective_learning",
        label="单有效学习成本",
        group="unit_economics",
        definition="窗口总 AI 成本除以有效学习成功会员数；收入未接入时只展示成本侧。",
        authority="bi_service",
        trust_level="B",
        owner="boss",
        drilldown="unit_economics",
    ),
    BIMetricDefinition(
        metric_id="data_trust_score",
        label="数据可信度分",
        group="data_trust",
        definition="基于接口降级、数据源缺口、指标口径完整度和更新时间形成的可信度摘要。",
        authority="bi_service",
        trust_level="A",
        owner="engineering",
        drilldown="data_trust",
    ),
)


def metric_by_id(metric_id: str) -> BIMetricDefinition:
    normalized = str(metric_id or "").strip()
    for metric in BI_METRICS:
        if metric.metric_id == normalized:
            return metric
    raise KeyError(f"Unknown BI metric: {metric_id}")
