from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileProbe:
    id: str
    section_id: str
    topic: str
    question_stem: str
    options: tuple[tuple[str, str, str], ...]


PROFILE_PROBES: tuple[ProfileProbe, ...] = (
    ProfileProbe(
        id="profile_review_rhythm_v1",
        section_id="learning_habits",
        topic="review_rhythm",
        question_stem="复习一章内容后，你更容易坚持哪种复盘方式？",
        options=(
            ("A", "当天用 5 分钟回看错因", "same_day_review"),
            ("B", "隔一两天集中整理错题", "delayed_batch_review"),
            ("C", "等到做综合题时再回看", "application_review"),
            ("D", "目前还没有固定复盘方式", "needs_review_structure"),
        ),
    ),
    ProfileProbe(
        id="profile_planning_style_v1",
        section_id="learning_habits",
        topic="planning_style",
        question_stem="面对一周学习任务，你更希望系统怎么安排？",
        options=(
            ("A", "每天给我明确的小任务", "daily_micro_plan"),
            ("B", "先给周目标，我自己拆分", "weekly_goal_plan"),
            ("C", "根据错题自动调整", "adaptive_error_plan"),
            ("D", "我通常临近考试才集中推进", "needs_pace_support"),
        ),
    ),
    ProfileProbe(
        id="profile_pressure_recovery_v1",
        section_id="pressure_state",
        topic="pressure_response",
        question_stem="连续做错几道题时，哪种帮助最适合你继续学下去？",
        options=(
            ("A", "先给一个同类简单例题找回手感", "worked_example"),
            ("B", "把步骤拆细一点，逐步提示", "minimal_scaffold"),
            ("C", "直接指出我最该补的知识点", "targeted_micro_drill"),
            ("D", "先降低节奏，给我一个短复盘", "pace_recovery"),
        ),
    ),
    ProfileProbe(
        id="profile_explanation_density_v1",
        section_id="teaching_preferences",
        topic="explanation_density",
        question_stem="你更喜欢 AI 怎样讲解建筑实务题？",
        options=(
            ("A", "先讲结论，再补关键依据", "concise_then_reason"),
            ("B", "按考试答题步骤完整展开", "step_by_step"),
            ("C", "多给工程现场类比", "scenario_analogy"),
            ("D", "先让我自己判断，再给提示", "hint_first"),
        ),
    ),
)


def get_profile_probes() -> tuple[ProfileProbe, ...]:
    return PROFILE_PROBES
