from __future__ import annotations

from dataclasses import dataclass


MIN_FORM_ROTATION_COUNT = 3
TARGET_FORM_ROTATION_COUNT = 5

# 题源声明（表单 v2 §6.2-v2 读侧聚合裁决）：section 可声明消费编译轻练权威
# （luban_lesson compiled practice authority，read-side aggregation——不写
# questions_bank、不复制数据、不造第二题库）。默认题源保持 questions_bank。
QUESTIONS_BANK_QUESTION_SOURCE = "questions_bank"
COMPILED_PRACTICE_QUESTION_SOURCE = "compiled_practice"
# 编译轻练读源产出的 candidate source_type 标记（只存在于读侧投影/组卷快照，
# 绝不回写 questions_bank）。
COMPILED_PRACTICE_SOURCE_TYPE = "COMPILED_PRACTICE"
# manifest 钉选导入的案例变式题 source_type 标记（新内容,不在任何库;
# provenance=manifest:<manifest sha256>,见 manifest_form_import.py）。
MANIFEST_SOURCE_TYPE = "FORM_MANIFEST"


@dataclass(frozen=True)
class AssessmentSection:
    id: str
    label: str
    count: int
    scored: bool
    question_types: tuple[str, ...]
    fallback_question_types: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ("REAL_EXAM", "TEXTBOOK_ASSESSMENT", "TEXTBOOK", "textbook_exercise")
    topics: tuple[str, ...] = ()
    minimum_multiplier: int = 3
    hard_require_calculation: bool = False
    strict_topics: bool = False
    # Item→dimension binding matrix (过线体检 §7.1): every scored item maps to
    # exactly one ability dimension via its section. Empty = no binding.
    ability_dimension: str = ""
    # 题源路由（§6.2-v2）：questions_bank（默认，Supabase 供给面）或
    # compiled_practice（编译轻练权威读侧聚合；此时 compiled_packs 声明该
    # section 的 pack 车道，只取 eligible∧signed 单选题）。
    question_source: str = QUESTIONS_BANK_QUESTION_SOURCE
    compiled_packs: tuple[str, ...] = ()
    # 表单 v2 题源政策（§6.2-v2 拍板②）：真题只做锚、不直接出。置 True 时
    # 组卷选材层过滤带真题 based_on/source 标记的行（source_type=REAL_EXAM
    # 已被 source_types 排除，此闸再挡练习册里"真题原题换皮入库"的标记行）。
    exclude_real_exam_marked: bool = False


@dataclass(frozen=True)
class AssessmentBlueprint:
    version: str
    requested_count: int
    sections: tuple[AssessmentSection, ...]
    assessment_type: str = "diagnostic"
    subject_id: str = "construction_exam"
    # Midpoint hard checkpoint (过线体检 §6.2): after this many scored tasks the
    # journey may surface a coarse band. 0 = no checkpoint.
    # v2 起支持多级检查点（§6.2-v2：第 10 题粗带 → 第 30 题客观带 → 全部完成
    # 精带）：checkpoints 声明全部检查点；checkpoint_after 保留单值语义
    # （= 第一个检查点），v1 消费方零改动。
    checkpoint_after: int = 0
    checkpoints: tuple[int, ...] = ()

    @property
    def checkpoint_list(self) -> tuple[int, ...]:
        """全部检查点（升序）。未声明 checkpoints 时回落到单值 checkpoint_after。"""
        if self.checkpoints:
            return tuple(int(item) for item in self.checkpoints)
        return (int(self.checkpoint_after),) if self.checkpoint_after else ()

    @property
    def scored_count(self) -> int:
        return sum(section.count for section in self.sections if section.scored)

    @property
    def profile_count(self) -> int:
        return sum(section.count for section in self.sections if not section.scored)


DIAGNOSTIC_V1 = AssessmentBlueprint(
    version="diagnostic_v1",
    requested_count=20,
    sections=(
        AssessmentSection(
            id="foundation_deep_foundation",
            label="地基基础 / 深基坑",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("地基基础", "深基坑"),
        ),
        AssessmentSection(
            id="main_structure",
            label="主体结构 / 混凝土 / 钢筋",
            count=3,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("主体结构", "混凝土", "钢筋"),
        ),
        AssessmentSection(
            id="waterproof_decoration_mep",
            label="防水 / 装饰 / 机电",
            count=3,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("防水", "装饰", "机电"),
        ),
        AssessmentSection(
            id="formwork_safety",
            label="模板脚手架 / 安全管理",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("模板", "脚手架", "安全"),
        ),
        AssessmentSection(
            id="planning_schedule",
            label="施工组织 / 网络计划",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("施工组织", "网络计划", "进度计划"),
        ),
        AssessmentSection(
            id="claim_quality_acceptance",
            label="合同索赔 / 质量验收",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("索赔", "质量验收", "合同"),
        ),
        AssessmentSection(
            id="comprehensive_application",
            label="综合案例 / 计算",
            count=2,
            scored=True,
            question_types=("case_study", "calculation"),
            fallback_question_types=("structured_judgment", "case_study"),
            topics=("综合案例", "计算", "网络计划", "索赔"),
            hard_require_calculation=False,
        ),
        AssessmentSection(
            id="learning_habits",
            label="学习习惯",
            count=2,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("review_rhythm", "planning_style", "error_review_style"),
        ),
        AssessmentSection(
            id="pressure_state",
            label="心理/状态",
            count=1,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("pressure_response", "frustration_recovery"),
        ),
        AssessmentSection(
            id="teaching_preferences",
            label="教学偏好",
            count=1,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("explanation_density", "hint_style", "practice_mode"),
        ),
    ),
)


TOPIC_WATERPROOF_V1 = AssessmentBlueprint(
    version="topic_waterproof_v1",
    requested_count=12,
    sections=(
        AssessmentSection(
            id="waterproof_materials",
            label="防水材料与构造",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            fallback_question_types=("single_choice", "multi_choice", "case_study"),
            topics=("防水", "卷材", "涂膜", "屋面"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
            strict_topics=True,
        ),
        AssessmentSection(
            id="waterproof_construction",
            label="防水施工与节点",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            fallback_question_types=("single_choice", "multi_choice", "case_study"),
            topics=("防水", "施工缝", "后浇带", "搭接", "节点"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
            strict_topics=True,
        ),
        AssessmentSection(
            id="waterproof_quality",
            label="防水质量与验收",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            fallback_question_types=("single_choice", "multi_choice", "case_study"),
            topics=("防水", "渗漏", "蓄水", "验收", "质量"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
            strict_topics=True,
        ),
    ),
)


REAL_EXAM_SIMULATION_MINI_V1 = AssessmentBlueprint(
    version="real_exam_simulation_mini_v1",
    requested_count=20,
    assessment_type="real_exam_simulation",
    subject_id="construction_exam",
    sections=(
        AssessmentSection(
            id="real_exam_foundation_structure",
            label="地基基础 / 主体结构",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            fallback_question_types=("single_choice", "multi_choice", "structured_judgment"),
            topics=("地基基础", "主体结构", "混凝土", "钢筋"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
        ),
        AssessmentSection(
            id="real_exam_waterproof_decoration_mep",
            label="防水 / 装饰 / 机电",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            fallback_question_types=("single_choice", "multi_choice", "structured_judgment"),
            topics=("防水", "装饰", "机电"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
        ),
        AssessmentSection(
            id="real_exam_formwork_safety",
            label="模板脚手架 / 安全",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            fallback_question_types=("single_choice", "multi_choice", "structured_judgment"),
            topics=("模板", "脚手架", "安全"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
        ),
        AssessmentSection(
            id="real_exam_schedule_claim",
            label="进度计划 / 合同索赔",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            fallback_question_types=("single_choice", "multi_choice", "structured_judgment"),
            topics=("进度计划", "网络计划", "合同", "索赔"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
        ),
        AssessmentSection(
            id="real_exam_quality_comprehensive",
            label="质量验收 / 综合应用",
            count=4,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            fallback_question_types=("single_choice", "multi_choice", "structured_judgment"),
            topics=("质量验收", "检验批", "综合案例", "计算"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
        ),
    ),
)


# 过线体检 acquisition diagnostic (plan 2026-08-04 §6.2/§11 Phase 2).
# Pure-tap constraint is binding: every scored task is single_choice or
# multi_choice option-tap — no free text, no drag-sort, no new answer-wire
# format. 12 scored tasks + 3 non-scored preparation-context probes, with the
# 6-task coarse-band checkpoint expressed as blueprint metadata.
PASS_READINESS_ARCHITECTURE_V1 = AssessmentBlueprint(
    version="pass_readiness_architecture_v1",
    requested_count=15,
    assessment_type="pass_readiness",
    subject_id="construction_exam",
    checkpoint_after=6,
    sections=(
        AssessmentSection(
            id="pr_objective_single",
            label="真题客观 · 主体结构/混凝土/钢筋",
            count=2,
            scored=True,
            question_types=("single_choice",),
            fallback_question_types=("single_choice", "multi_choice"),
            topics=("主体结构", "混凝土", "钢筋"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr_objective_multi",
            label="真题客观 · 多选/条件判断",
            count=2,
            scored=True,
            question_types=("multi_choice",),
            fallback_question_types=("single_choice", "multi_choice"),
            topics=("主体结构", "安全", "质量验收"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr_case_safety",
            label="案例点选 · 安全/危大工程",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("安全", "脚手架", "模板", "危大工程"),
            ability_dimension="construction_logic",
        ),
        AssessmentSection(
            id="pr_case_schedule",
            label="案例点选 · 进度/网络计划(选出正确顺序)",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("进度计划", "网络计划", "施工组织"),
            ability_dimension="construction_logic",
        ),
        AssessmentSection(
            id="pr_case_quality",
            label="案例点选 · 质量/验收(选出错误项)",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("质量验收", "检验批", "质量"),
            ability_dimension="case_scoring_point_recognition",
        ),
        AssessmentSection(
            id="pr_answer_discrimination",
            label="得分表述辨析 · 防水(轮换槽)",
            count=1,
            scored=True,
            question_types=("single_choice",),
            fallback_question_types=("single_choice", "multi_choice"),
            topics=("防水", "屋面", "渗漏"),
            ability_dimension="case_scoring_point_recognition",
        ),
        AssessmentSection(
            id="pr_scoring_point_recognition",
            label="采分点识别(点选)",
            count=1,
            scored=True,
            question_types=("multi_choice",),
            fallback_question_types=("single_choice", "multi_choice"),
            topics=("质量验收", "防水", "综合案例"),
            ability_dimension="case_scoring_point_recognition",
        ),
        AssessmentSection(
            id="pr_prep_context",
            label="备考背景",
            count=3,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("attempt_history", "recent_score_band", "weekly_study_hours"),
        ),
    ),
)


# ── 过线体检表单 v2（§6.2-v2 owner 拍板 2026-08-06）────────────────────────
# 39 交互 = 30 客观（20 单选=编译轻练变式池五族配额 + 10 多选=练习册源、
# 过滤真题标记）+ 3 段案例结构化 6 题 + 3 备考背景 probe。
# 两级检查点：第 10 题粗带 → 第 30 题客观带 → 全部完成精带。
# v1 blueprint 原样保留（回滚锚），不动。
#
# 五族 pack 车道 = 题源盘点 2026-08-06 §5.1 清洁包口径（排除 EXCLUSION-01..04
# 与 N-1/2/3 待裁决包），五族 eligible 单选 51/29/32/60/41（余量 10.6×）。
PASS_READINESS_ARCHITECTURE_V2 = AssessmentBlueprint(
    version="pass_readiness_architecture_v2",
    requested_count=39,
    assessment_type="pass_readiness",
    subject_id="construction_exam",
    checkpoint_after=10,
    checkpoints=(10, 30),
    sections=(
        # ── 20 单选：编译轻练变式池，五族配额各 4（core_knowledge ≈20 观察）──
        AssessmentSection(
            id="pr2_single_main_structure",
            label="真题变式客观 · 主体结构",
            count=5,
            scored=True,
            question_types=("single_choice",),
            question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
            compiled_packs=("C01", "C04", "C05", "C07", "Q01", "Q02"),
            topics=("主体结构", "混凝土", "钢筋"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr2_single_safety",
            label="真题变式客观 · 安全",
            count=4,
            scored=True,
            question_types=("single_choice",),
            question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
            compiled_packs=("J01", "R01", "S05", "S06"),
            topics=("安全", "脚手架", "危大工程"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr2_single_schedule",
            label="真题变式客观 · 进度",
            count=3,
            scored=True,
            question_types=("single_choice",),
            question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
            compiled_packs=("E05", "N01", "N02", "N03"),
            topics=("进度计划", "网络计划", "施工组织"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr2_single_quality",
            label="真题变式客观 · 质量验收",
            count=4,
            scored=True,
            question_types=("single_choice",),
            question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
            compiled_packs=("A02", "G01", "G02", "G03", "G04"),
            topics=("质量验收", "检验批", "质量"),
            ability_dimension="core_knowledge",
        ),
        AssessmentSection(
            id="pr2_single_waterproof",
            label="真题变式客观 · 防水",
            count=4,
            scored=True,
            question_types=("single_choice",),
            question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
            compiled_packs=("F02", "F03", "F05", "F16"),
            topics=("防水", "屋面", "渗漏"),
            ability_dimension="core_knowledge",
        ),
        # ── 10 多选：questions_bank 练习册源过渡（§6.2-v2：非真题原题；
        # v2.1 由变体拼装器+双签替换为真变式）。construction_logic ≈10 观察。──
        AssessmentSection(
            id="pr2_objective_multi",
            label="客观多选 · 条件判断/多选风险",
            count=10,
            scored=True,
            question_types=("multi_choice",),
            source_types=("TEXTBOOK", "textbook_exercise"),
            exclude_real_exam_marked=True,
            topics=("主体结构", "安全", "进度计划", "质量验收", "防水"),
            minimum_multiplier=MIN_FORM_ROTATION_COUNT,
            ability_dimension="construction_logic",
        ),
        # ── 3 段案例结构化 × 2 题（case_scoring_point_recognition ≈6 观察）──
        AssessmentSection(
            id="pr2_case_safety",
            label="案例点选 · 安全/危大工程",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("安全", "脚手架", "模板", "危大工程"),
            ability_dimension="case_scoring_point_recognition",
        ),
        AssessmentSection(
            id="pr2_case_schedule",
            label="案例点选 · 进度/网络计划(选出正确顺序)",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("进度计划", "网络计划", "施工组织"),
            ability_dimension="case_scoring_point_recognition",
        ),
        AssessmentSection(
            id="pr2_case_quality",
            label="案例点选 · 质量/验收(选出错误项)",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice"),
            topics=("质量验收", "检验批", "质量"),
            ability_dimension="case_scoring_point_recognition",
        ),
        # ── 3 备考背景 probe（复用 pr_prep_context 注册 probe，零新增槽）──
        AssessmentSection(
            id="pr_prep_context",
            label="备考背景",
            count=3,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("attempt_history", "recent_score_band", "weekly_study_hours"),
        ),
    ),
)


_BLUEPRINTS = {
    DIAGNOSTIC_V1.version: DIAGNOSTIC_V1,
    TOPIC_WATERPROOF_V1.version: TOPIC_WATERPROOF_V1,
    REAL_EXAM_SIMULATION_MINI_V1.version: REAL_EXAM_SIMULATION_MINI_V1,
    PASS_READINESS_ARCHITECTURE_V1.version: PASS_READINESS_ARCHITECTURE_V1,
    PASS_READINESS_ARCHITECTURE_V2.version: PASS_READINESS_ARCHITECTURE_V2,
}


def real_exam_source_policy(
    *,
    real_exam_share: float,
    provenance_ok: bool = False,
    teaching_signoff: bool = False,
) -> dict[str, str | float | bool]:
    share = max(0.0, min(1.0, float(real_exam_share or 0.0)))
    if share >= 0.6:
        label = "真题样式测评"
        copy = "本次真题样式测评用于校准综合应用能力，不代表官方考试分数。"
    else:
        label = "综合模拟测评"
        copy = "本次综合模拟测评用于校准综合应用能力，不代表官方考试分数。"
    if share >= 0.95 and provenance_ok and teaching_signoff:
        official_allowed = True
    else:
        official_allowed = False
    return {
        "source_policy_label": label,
        "user_copy": copy,
        "real_exam_share": share,
        "official_real_exam_label_allowed": official_allowed,
    }


def ability_dimensions_by_section(version: str) -> dict[str, str]:
    """Section→ability-dimension binding matrix for a blueprint (§7.1).

    Empty dict when the blueprint declares no bindings (all non-pass-readiness
    blueprints today).
    """

    blueprint = get_assessment_blueprint(version)
    return {
        section.id: section.ability_dimension
        for section in blueprint.sections
        if section.scored and section.ability_dimension
    }


def get_assessment_blueprint(version: str = "diagnostic_v1") -> AssessmentBlueprint:
    try:
        return _BLUEPRINTS[version]
    except KeyError as exc:
        try:
            from deeptutor.services.assessment.topic_catalog import (
                build_topic_assessment_blueprint,
                topic_id_from_blueprint_version,
            )

            return build_topic_assessment_blueprint(topic_id_from_blueprint_version(version))
        except ValueError:
            raise ValueError(f"Unknown assessment blueprint: {version}") from exc
