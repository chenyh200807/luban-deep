from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deeptutor.services.assessment.blueprint import (
    MIN_FORM_ROTATION_COUNT,
    TARGET_FORM_ROTATION_COUNT,
    AssessmentBlueprint,
    AssessmentSection,
)

TopicTestSetStatus = Literal["stable", "pilot", "authoring_needed"]

REQUIRED_TOPIC_TESTSET_IDS = (
    "waterproof",
    "decoration",
    "mep",
    "foundation",
    "main_structure",
    "formwork_scaffold",
    "safety",
    "schedule",
    "contract_claim",
    "quality_acceptance",
)


@dataclass(frozen=True)
class TopicSectionSpec:
    id: str
    label: str
    topics: tuple[str, ...]


@dataclass(frozen=True)
class TopicTestSetSpec:
    topic_id: str
    label: str
    short_label: str
    description: str
    sections: tuple[TopicSectionSpec, ...]

    @property
    def blueprint_version(self) -> str:
        return f"topic_{self.topic_id}_v1"


class TopicTestSetUnavailable(ValueError):
    pass


_TOPIC_TESTSET_CATALOG: tuple[TopicTestSetSpec, ...] = (
    TopicTestSetSpec(
        topic_id="waterproof",
        label="防水工程",
        short_label="防水",
        description="材料构造、施工节点、质量验收",
        sections=(
            TopicSectionSpec("materials", "防水材料与构造", ("防水", "卷材", "涂膜", "屋面")),
            TopicSectionSpec("construction", "防水施工与节点", ("防水", "施工缝", "后浇带", "搭接", "节点")),
            TopicSectionSpec("quality", "防水质量与验收", ("防水", "渗漏", "蓄水", "验收", "质量")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="decoration",
        label="装饰装修",
        short_label="装饰",
        description="抹灰饰面、吊顶隔墙、幕墙门窗",
        sections=(
            TopicSectionSpec("plaster_finish", "抹灰与饰面", ("抹灰", "饰面", "面砖", "装饰")),
            TopicSectionSpec("ceiling_partition", "吊顶与隔墙", ("吊顶", "轻质隔墙", "隔墙", "龙骨")),
            TopicSectionSpec("curtain_wall_opening", "幕墙与门窗", ("幕墙", "门窗", "玻璃", "密封")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="mep",
        label="建筑机电",
        short_label="机电",
        description="电气、给排水、通风空调与设备",
        sections=(
            TopicSectionSpec("electrical", "建筑电气", ("电气", "配电", "照明", "接地")),
            TopicSectionSpec("plumbing", "给排水", ("给水", "排水", "管道", "试压")),
            TopicSectionSpec("hvac_equipment", "通风空调与设备", ("通风", "空调", "设备", "风管")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="foundation",
        label="地基基础",
        short_label="基础",
        description="地基处理、桩基、基坑与土方",
        sections=(
            TopicSectionSpec("ground_treatment", "地基处理与桩基", ("地基", "桩", "基础", "承载力")),
            TopicSectionSpec("pit_support", "基坑支护与降水", ("基坑", "支护", "降水", "开挖")),
            TopicSectionSpec("earthwork", "土方与验槽", ("土方", "验槽", "回填", "钎探")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="main_structure",
        label="主体结构",
        short_label="主体",
        description="混凝土、钢筋、砌体与结构施工",
        sections=(
            TopicSectionSpec("concrete", "混凝土工程", ("混凝土", "浇筑", "养护", "施工缝")),
            TopicSectionSpec("rebar", "钢筋工程", ("钢筋", "连接", "绑扎", "保护层")),
            TopicSectionSpec("masonry_structure", "砌体与结构施工", ("砌体", "主体结构", "结构", "墙体")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="formwork_scaffold",
        label="模板脚手架",
        short_label="模架",
        description="模板支撑、脚手架、专项方案",
        sections=(
            TopicSectionSpec("formwork", "模板工程", ("模板", "支撑", "拆模", "起拱")),
            TopicSectionSpec("scaffold", "脚手架", ("脚手架", "脚手", "连墙件", "立杆")),
            TopicSectionSpec("special_plan", "专项方案", ("专项方案", "专家论证", "危险性", "安全")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="safety",
        label="安全管理",
        short_label="安全",
        description="安全责任、临时用电、文明施工",
        sections=(
            TopicSectionSpec("safety_responsibility", "安全责任与制度", ("安全", "责任", "制度", "交底")),
            TopicSectionSpec("temporary_power", "临时用电与防护", ("临时用电", "开关箱", "防护", "接地")),
            TopicSectionSpec("civilized_incident", "文明施工与事故", ("文明施工", "事故", "应急", "隐患")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="schedule",
        label="进度计划",
        short_label="进度",
        description="网络计划、关键线路、工期控制",
        sections=(
            TopicSectionSpec("network_plan", "网络计划", ("网络计划", "关键线路", "时差", "双代号")),
            TopicSectionSpec("duration_control", "工期控制", ("工期", "进度", "压缩", "延误")),
            TopicSectionSpec("flow_construction", "流水施工", ("流水施工", "流水步距", "节拍", "施工段")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="contract_claim",
        label="合同索赔",
        short_label="索赔",
        description="合同管理、变更、索赔与结算",
        sections=(
            TopicSectionSpec("contract", "合同管理", ("合同", "总包", "分包", "履约")),
            TopicSectionSpec("change_claim", "变更与索赔", ("变更", "索赔", "签证", "费用")),
            TopicSectionSpec("settlement", "结算与价款", ("结算", "价款", "预付款", "进度款")),
        ),
    ),
    TopicTestSetSpec(
        topic_id="quality_acceptance",
        label="质量验收",
        short_label="验收",
        description="检验批、材料复验、质量整改",
        sections=(
            TopicSectionSpec("inspection_lot", "检验批与验收", ("检验批", "验收", "分项", "分部")),
            TopicSectionSpec("material_retest", "材料复验", ("复验", "见证取样", "材料", "试验")),
            TopicSectionSpec("quality_rectification", "质量整改", ("质量", "整改", "缺陷", "事故")),
        ),
    ),
)


def get_topic_testset_catalog() -> tuple[TopicTestSetSpec, ...]:
    return _TOPIC_TESTSET_CATALOG


def get_topic_testset_spec(topic_id: str) -> TopicTestSetSpec:
    normalized = _normalize_topic_id(topic_id)
    for spec in _TOPIC_TESTSET_CATALOG:
        if spec.topic_id == normalized:
            return spec
    raise TopicTestSetUnavailable(f"Unsupported assessment topic: {topic_id}")


def resolve_topic_testset_spec(topic_ids: list[str] | tuple[str, ...]) -> TopicTestSetSpec:
    for topic_id in topic_ids:
        normalized = _normalize_topic_id(topic_id)
        if normalized:
            return get_topic_testset_spec(normalized)
    return get_topic_testset_spec("waterproof")


def build_topic_assessment_blueprint(topic_id: str) -> AssessmentBlueprint:
    spec = get_topic_testset_spec(topic_id)
    return AssessmentBlueprint(
        version=spec.blueprint_version,
        requested_count=12,
        sections=tuple(
            AssessmentSection(
                id=f"{spec.topic_id}_{section.id}",
                label=section.label,
                count=4,
                scored=True,
                question_types=("single_choice", "multi_choice"),
                fallback_question_types=("single_choice", "multi_choice", "case_study"),
                topics=section.topics,
                minimum_multiplier=MIN_FORM_ROTATION_COUNT,
                strict_topics=True,
            )
            for section in spec.sections
        ),
    )


def topic_id_from_blueprint_version(blueprint_version: str) -> str:
    text = str(blueprint_version or "").strip()
    if text.startswith("topic_") and text.endswith("_v1"):
        return text[len("topic_") : -len("_v1")]
    raise TopicTestSetUnavailable(f"Unsupported topic blueprint: {blueprint_version}")


def classify_topic_form_count(form_count: int) -> TopicTestSetStatus:
    count = max(0, int(form_count or 0))
    if count >= TARGET_FORM_ROTATION_COUNT:
        return "stable"
    if count >= MIN_FORM_ROTATION_COUNT:
        return "pilot"
    return "authoring_needed"


def recommend_assessment_entry(
    topics: list[dict[str, object]],
    *,
    weak_nodes: list[dict[str, object]],
    has_assessment_history: bool,
) -> dict[str, object]:
    enabled_topic_ids = {
        str(item.get("topic_id") or "")
        for item in topics
        if item.get("enabled") is True and str(item.get("topic_id") or "")
    }
    sorted_weak_nodes = sorted(
        list(weak_nodes or []),
        key=lambda item: int(item.get("mastery") or 0),
    )
    for weak_node in sorted_weak_nodes:
        topic_id = _topic_id_from_learning_label(str(weak_node.get("name") or ""))
        if topic_id and topic_id in enabled_topic_ids:
            spec = get_topic_testset_spec(topic_id)
            return {
                "recommended_mode": "topic",
                "recommended_topic_id": topic_id,
                "recommended_label": f"{spec.label}专题测评",
                "recommended_count": 12,
                "reason": f"近期 {spec.short_label} 相关证据偏弱，建议先做一次专题测评。",
                "source": "learner_state_weak_node",
                "confidence": "medium" if has_assessment_history else "low",
            }
    return {
        "recommended_mode": "diagnostic",
        "recommended_topic_id": "",
        "recommended_label": "综合摸底",
        "recommended_count": 20,
        "reason": "当前专题证据还不够稳定，建议先做 20 题综合摸底校准能力结构。",
        "source": "insufficient_learning_signal",
        "confidence": "low",
    }


def _normalize_topic_id(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _topic_id_from_learning_label(label: str) -> str:
    text = str(label or "")
    aliases: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("waterproof", ("防水", "卷材", "涂膜", "屋面")),
        ("decoration", ("装饰", "装修", "抹灰", "饰面", "吊顶", "幕墙", "门窗")),
        ("mep", ("机电", "电气", "给排水", "通风", "空调", "设备")),
        ("foundation", ("地基", "基础", "基坑", "桩", "土方", "验槽")),
        ("main_structure", ("主体", "主体结构", "混凝土", "钢筋", "砌体", "施工缝")),
        ("formwork_scaffold", ("模板", "脚手架", "脚手", "专项方案", "专家论证")),
        ("safety", ("安全", "临时用电", "文明施工", "事故", "隐患")),
        ("schedule", ("进度", "网络计划", "流水施工", "工期", "关键线路", "时差")),
        ("contract_claim", ("合同", "索赔", "变更", "签证", "结算", "价款")),
        ("quality_acceptance", ("质量验收", "检验批", "复验", "见证取样", "整改", "质量")),
    )
    for topic_id, keywords in aliases:
        if any(keyword in text for keyword in keywords):
            return topic_id
    return ""
