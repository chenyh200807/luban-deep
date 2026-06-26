"""Cross-cutting acceptance tests for the question lifecycle wire (Tasks 4-5).

These tests prove that scene → skill composition behaves the same whether the
caller is deep_question, question_followup, or the TutorBot loop. The
single-loader invariant from Task 2.5 means there is only one path to test;
this file is the cross-cutting check that the Task 3 wire + Task 2.5 shim
together satisfy the Task 4 (follow-up + grading) and Task 5 (TutorBot scene
sync) acceptance criteria.

Plan: docs/plan/题目生命周期与助教运行时/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.question_lifecycle_skills import (
    SCENE_COMPOSITION,
    attach_question_lifecycle_scene_to_context,
    build_question_lifecycle_skill_context,
    derive_question_lifecycle_scene,
    looks_like_full_case_answer_submission,
    split_full_case_answer_submission,
)


@dataclass
class _FakeContext:
    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _mcq_followup_context() -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question_type": "mcq",
        "question": "下列哪个选项正确？",
        "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    }


def _case_followup_context() -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question_type": "case",
        "question": "案例题：分析施工方案不妥之处...",
    }


# ---------------------------------------------------------------------------
# Task 4 — follow-up + grading scene selection
# ---------------------------------------------------------------------------


def test_mcq_grading_loads_construction_mcq_grading_skill():
    """Submitted MCQ answer → mcq_grading scene → construction-mcq-grading SKILL."""
    ctx = _FakeContext(user_message="B", metadata={"question_followup_context": _mcq_followup_context()})
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "mcq_grading"
    skill_ctx = build_question_lifecycle_skill_context(ctx)
    assert "construction-mcq-grading" in skill_ctx.skill_names
    assert "# Construction MCQ Grading" in skill_ctx.instructions


def test_case_grading_loads_construction_case_grading_skill():
    ctx = _FakeContext(
        user_message="施工单位应组织专家论证危大工程方案",
        metadata={"question_followup_context": _case_followup_context()},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "case_grading"
    skill_ctx = build_question_lifecycle_skill_context(ctx)
    assert "construction-case-grading" in skill_ctx.skill_names
    assert "# Construction Case Grading" in skill_ctx.instructions


def test_free_text_case_grading_loads_no_fake_score_guard():
    ctx = _FakeContext(
        user_message=(
            "案例：二次结构填充墙施工时，项目部把刚生产7天的蒸压加气混凝土砌块用于砌筑。"
            "我的答案：不妥，应龄期28天，含水率宜小于30%。帮我按踩分点批改，简短"
        )
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "case_grading"
    skill_ctx = build_question_lifecycle_skill_context(ctx)
    assert "construction-case-grading" in skill_ctx.skill_names
    assert "模型常识" in skill_ctx.instructions
    assert "本次不硬估标准分" in skill_ctx.instructions


def test_case_grading_detects_exam_sheet_answer_layout():
    ctx = _FakeContext(
        user_message=(
            "【背景资料】某施工单位中标新建教学楼工程。\n"
            "【问题】\n"
            "现场质量检查的“三检”制度是哪三检？\n"
            "回答\n"
            "作答：\n"
            "“三检”制度是指自检、互检、专检。"
        )
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "case_grading"


def test_full_case_answer_submission_predicate_is_shared_runtime_guard():
    text = (
        "【背景资料】某施工单位中标新建教学楼工程。\n"
        "【问题】\n"
        "现场质量检查的“三检”制度是哪三检？\n"
        "回答\n"
        "作答：\n"
        "“三检”制度是指自检、互检、专检。"
    )
    assert looks_like_full_case_answer_submission(text)
    stem, answer = split_full_case_answer_submission(text)
    assert "【问题】" in stem
    assert answer == "“三检”制度是指自检、互检、专检。"
    assert not looks_like_full_case_answer_submission("这个案例题第1问为什么错？")


def test_full_case_answer_submission_accepts_inline_problem_marker_with_case_context():
    text = (
        "案例背景：某施工单位承接一项工程。问题：指出施工现场质量检查制度包括哪些内容。"
        " 作答：施工现场质量检查包括自检、互检、专检。"
    )
    ctx = _FakeContext(user_message=text)

    assert attach_question_lifecycle_scene_to_context(ctx) == "case_grading"
    assert looks_like_full_case_answer_submission(text)
    stem, answer = split_full_case_answer_submission(text)
    assert "问题：指出施工现场质量检查制度" in stem
    assert answer == "施工现场质量检查包括自检、互检、专检。"


def test_case_grading_detects_case_background_answer_layout():
    ctx = _FakeContext(
        user_message=(
            "案例背景：某工程地下室混凝土拆模后发现孔洞。\n"
            "问题：补充孔洞治理流程。\n"
            "作答：凿毛、涂刷界面剂、支模、浇筑、养护。"
        )
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "case_grading"


def test_pre_submission_followup_loads_question_review_skill():
    """Plan Task 4 Step 1 #1: pre-answer follow-up → question_review."""
    ctx = _FakeContext(
        user_message="这道题怎么做",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "question_review"
    skill_ctx = build_question_lifecycle_skill_context(ctx)
    assert "construction-question-review" in skill_ctx.skill_names


def test_grading_takes_priority_over_generation_in_mixed_turn():
    """Plan §6.5 v2-1: mixed-turn `答 B 再出 3 题` → mcq_grading, not practice_generation."""
    ctx = _FakeContext(
        user_message="B，再出 3 题",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "mcq_grading"


# ---------------------------------------------------------------------------
# Task 5 — TutorBot scene names share with deep_question via single loader
# ---------------------------------------------------------------------------


def test_tutorbot_practice_generation_resolves_to_supply_skill():
    """Plan Task 5 #3: "再出3题" routes to deep_question via lifecycle builder."""
    ctx = _FakeContext(user_message="再出3题")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "practice_generation"
    assert SCENE_COMPOSITION[scene] == (
        "construction-exam-tutor",
        "construction-question-supply",
    )


def test_tutorbot_real_exam_request_resolves_to_review_skill():
    """Plan Task 5 #2: "分析一道真题" → question_review (free-text review intent).

    The caller (deep_question / TutorBot loop) is responsible for materializing a
    stem first if no active object exists, then re-running with the active
    object so subsequent submission turns route to mcq_grading / case_grading.
    """
    ctx = _FakeContext(user_message="分析一道真题")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "question_review"
    assert SCENE_COMPOSITION[scene] == (
        "construction-exam-tutor",
        "construction-question-review",
    )


def test_tutorbot_learning_support_intent_loads_support_skill():
    """Plan Task 5 #4."""
    ctx = _FakeContext(user_message="我没动力了")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "learning_support"
    assert SCENE_COMPOSITION[scene] == (
        "construction-exam-tutor",
        "construction-learning-support",
    )


def test_tutorbot_learning_evidence_story_intent():
    """Plan Task 5 #5."""
    ctx = _FakeContext(user_message="我最近哪里错")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "learning_evidence_story"
    assert SCENE_COMPOSITION[scene] == (
        "construction-exam-tutor",
        "construction-learning-evidence-story",
    )


def test_tutorbot_study_assistant_intent():
    """Plan Task 5 #6."""
    ctx = _FakeContext(user_message="今天学什么")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "study_assistant"
    assert SCENE_COMPOSITION[scene] == (
        "construction-exam-tutor",
        "construction-study-assistant",
    )


def test_tutorbot_study_plan_intent_loads_study_assistant_authority():
    """Study plans must use the existing study-assistant authority.

    The generic TutorBot teaching skill may phrase the answer, but it must not
    invent learner-stage or attempt-count facts when no learner-state evidence
    was projected into the turn.
    """

    ctx = _FakeContext(user_message="不看内部信息了，给我一个3天复盘计划，不要再出题。")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "study_assistant"
    skill_ctx = build_question_lifecycle_skill_context(ctx)
    assert skill_ctx.skill_names == (
        "construction-exam-tutor",
        "construction-study-assistant",
    )
    assert "不自行发明薄弱点、掌握度、题目优先级或长期计划" in skill_ctx.instructions
    assert "证据不足时断言" in skill_ctx.instructions


# ---------------------------------------------------------------------------
# §5.0 verification target #2: single loader invariant
# ---------------------------------------------------------------------------


def test_single_loader_invariant_via_grep_surrogate():
    """Surrogate for plan §5.0 verification target #2: no module other than
    SkillsLoader and question_lifecycle_skills should read construction-*
    SKILL.md files directly.

    teaching_modes' lecture-skill path is explicitly out of scope (plan §6.1
    R6 only governs construction scene skills) and remains as a known carve-out
    — see deeptutor/tutorbot/teaching_modes.py:_read_skill_file.
    """
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    forbidden_substrings = (
        "construction-exam-tutor",
        "construction-mcq-grading",
        "construction-case-grading",
        "construction-question-supply",
        "construction-question-review",
        "construction-learning-evidence-story",
        "construction-study-assistant",
        "construction-learning-support",
    )

    allowed_modules = {
        "deeptutor/tutorbot/agent/skills.py",
        "deeptutor/services/question_lifecycle_skills.py",
    }

    offenders: list[str] = []
    for py_file in (repo_root / "deeptutor").rglob("*.py"):
        rel = py_file.relative_to(repo_root).as_posix()
        if rel in allowed_modules:
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        # File-level prefilter: only inspect files that combine a forbidden
        # construction skill name with a raw file-read API. Plain docstring
        # mentions in unrelated files are OK.
        if ".read_text" not in text and "open(" not in text:
            continue
        for needle in forbidden_substrings:
            if needle not in text:
                continue
            # Check every line for "<needle> ... read_text/open" co-occurrence.
            # Each needle is checked independently (no premature break across
            # needles); reviewer noted earlier `break` skipped remaining
            # needles after the first match.
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if needle in stripped and (
                    "read_text" in stripped or "open(" in stripped
                ):
                    offenders.append(f"{rel}: {stripped[:120]}")
                    break  # found an offender for this needle, advance to next needle

    assert not offenders, (
        "Construction-scene SKILL.md files are read outside of SkillsLoader / "
        "question_lifecycle_skills (violates plan §5.0 verification target #2):\n"
        + "\n".join(offenders)
    )


def test_tutorbot_loop_does_not_redetect_lifecycle_scene():
    """TutorBot is an executor, not the question lifecycle scene authority."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    loop_path = repo_root / "deeptutor" / "tutorbot" / "agent" / "loop.py"
    text = loop_path.read_text(encoding="utf-8")

    assert "attach_question_lifecycle_scene_to_context" not in text
    assert "derive_question_lifecycle_scene" not in text
