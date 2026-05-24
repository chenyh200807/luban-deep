"""Cross-cutting acceptance tests for the question lifecycle wire (Tasks 4-5).

These tests prove that scene → skill composition behaves the same whether the
caller is deep_question, question_followup, or the TutorBot loop. The
single-loader invariant from Task 2.5 means there is only one path to test;
this file is the cross-cutting check that the Task 3 wire + Task 2.5 shim
together satisfy the Task 4 (follow-up + grading) and Task 5 (TutorBot scene
sync) acceptance criteria.

Plan: docs/plan/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.question_lifecycle_skills import (
    SCENE_COMPOSITION,
    attach_question_lifecycle_scene_to_context,
    build_question_lifecycle_skill_context,
    derive_question_lifecycle_scene,
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
    skill_ctx = build_question_lifecycle_skill_context(scene)
    assert "construction-mcq-grading" in skill_ctx.skill_names
    assert "# Construction MCQ Grading" in skill_ctx.instructions


def test_case_grading_loads_construction_case_grading_skill():
    ctx = _FakeContext(
        user_message="施工单位应组织专家论证危大工程方案",
        metadata={"question_followup_context": _case_followup_context()},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "case_grading"
    skill_ctx = build_question_lifecycle_skill_context(scene)
    assert "construction-case-grading" in skill_ctx.skill_names
    assert "# Construction Case Grading" in skill_ctx.instructions


def test_pre_submission_followup_loads_question_review_skill():
    """Plan Task 4 Step 1 #1: pre-answer follow-up → question_review."""
    ctx = _FakeContext(
        user_message="这道题怎么做",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "question_review"
    skill_ctx = build_question_lifecycle_skill_context(scene)
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
        for needle in forbidden_substrings:
            # Allow comments / docstring mentions; flag only Path(...).read_text-like patterns.
            if needle in text:
                # Heuristic: only fail if combined with .read_text or open(
                # in the same file. Plain mentions in docstrings are OK.
                if ".read_text" in text or "open(" in text:
                    # Make sure the mention is on a non-comment line.
                    for line in text.splitlines():
                        stripped = line.strip()
                        if needle in stripped and not stripped.startswith("#"):
                            if "read_text" in stripped or "open(" in stripped:
                                offenders.append(f"{rel}: {stripped[:100]}")
                                break
                break

    assert not offenders, (
        "Construction-scene SKILL.md files are read outside of SkillsLoader / "
        "question_lifecycle_skills (violates plan §5.0 verification target #2):\n"
        + "\n".join(offenders)
    )
