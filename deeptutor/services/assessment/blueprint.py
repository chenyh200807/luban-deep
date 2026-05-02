from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssessmentSection:
    id: str
    label: str
    count: int
    scored: bool
    question_types: tuple[str, ...]
    fallback_question_types: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ("REAL_EXAM", "TEXTBOOK_ASSESSMENT", "TEXTBOOK")
    topics: tuple[str, ...] = ()
    minimum_multiplier: int = 3
    hard_require_calculation: bool = False


@dataclass(frozen=True)
class AssessmentBlueprint:
    version: str
    requested_count: int
    sections: tuple[AssessmentSection, ...]

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


_BLUEPRINTS = {DIAGNOSTIC_V1.version: DIAGNOSTIC_V1}


def get_assessment_blueprint(version: str = "diagnostic_v1") -> AssessmentBlueprint:
    try:
        return _BLUEPRINTS[version]
    except KeyError as exc:
        raise ValueError(f"Unknown assessment blueprint: {version}") from exc
