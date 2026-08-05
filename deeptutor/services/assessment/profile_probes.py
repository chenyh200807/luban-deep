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
    # ── 过线体检 preparation-context probes (plan 2026-08-04 §6.2) ──────────
    # Non-scored, structurally excluded from ability scoring; consumed by
    # prep_feasibility / risk wording and the rolling-expiry CTA only.
    ProfileProbe(
        id="profile_pr_attempt_history_v1",
        section_id="pr_prep_context",
        topic="attempt_history",
        question_stem="你目前的一建备考经历是？（含已通过科目的情况）",
        options=(
            ("A", "首次报考，四科都还没过", "first_attempt"),
            ("B", "考过一次，去年已过部分公共科（管理/经济/法规）", "retaker_passed_public_last_year"),
            ("C", "考过不止一次，前年过的公共科成绩今年到期", "retaker_passes_expiring_this_year"),
            ("D", "只剩《建筑实务》一科未过", "retaker_only_practical_left"),
            ("E", "之前通过的科目已作废，相当于重新开始", "retaker_passes_lapsed"),
        ),
    ),
    ProfileProbe(
        id="profile_pr_recent_score_band_v1",
        section_id="pr_prep_context",
        topic="recent_score_band",
        question_stem="你最近一次《建筑实务》真实考试成绩大概在哪个分数段？（满分 160，过线 96）",
        options=(
            ("A", "没参加过实务考试", "no_prior_score"),
            ("B", "60 分以下", "below_60"),
            ("C", "60–79 分", "score_60_79"),
            ("D", "80–95 分", "score_80_95"),
            ("E", "96 分及以上（曾过线）", "score_96_plus"),
        ),
    ),
    ProfileProbe(
        id="profile_pr_weekly_study_hours_v1",
        section_id="pr_prep_context",
        topic="weekly_study_hours",
        question_stem="未来到考试前，你每周能稳定投入多少有效学习时间？",
        options=(
            ("A", "5 小时以内", "lt_5"),
            ("B", "5–10 小时", "5_10"),
            ("C", "10–20 小时", "10_20"),
            ("D", "20 小时以上", "gt_20"),
        ),
    ),
)


def get_profile_probes() -> tuple[ProfileProbe, ...]:
    return PROFILE_PROBES
