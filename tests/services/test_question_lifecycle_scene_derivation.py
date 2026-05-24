"""Tests for derive_question_lifecycle_scene (Plan §5.1 Single Decider Rule).

This is the implementation-point of scene authority for Tasks 3-5. ChatOrchestrator
(Task 0.7) may later escalate scene decision to a single earlier point, but for now
the derivation function lives next to the lifecycle builder and is consumed by
deep_question entry / question_followup / TutorBot loop with identical semantics.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any

import pytest

from deeptutor.services.question_lifecycle_skills import derive_question_lifecycle_scene


@dataclass
class _FakeContext:
    user_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _mcq_followup_context(answered: bool = False) -> dict[str, Any]:
    return {
        "question_id": "q1",
        "question_type": "mcq",
        "question": "下列哪个选项正确？",
        "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
    }


def test_no_active_object_practice_intent_returns_practice_generation():
    ctx = _FakeContext(user_message="再出 3 题")
    assert derive_question_lifecycle_scene(ctx) == "practice_generation"


def test_active_object_with_submission_returns_mcq_grading():
    ctx = _FakeContext(
        user_message="B",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


def test_active_object_without_submission_returns_question_review():
    ctx = _FakeContext(
        user_message="这道题怎么做",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "question_review"


def test_active_object_case_question_with_submission_returns_case_grading():
    case_ctx = {
        "question_id": "q1",
        "question_type": "case",
        "question": "案例题：分析该施工方案的不妥之处...",
    }
    ctx = _FakeContext(
        user_message="施工单位应组织专家论证危大工程方案",
        metadata={"question_followup_context": case_ctx},
    )
    assert derive_question_lifecycle_scene(ctx) == "case_grading"


def test_learning_evidence_story_intent():
    ctx = _FakeContext(user_message="我最近哪里错")
    assert derive_question_lifecycle_scene(ctx) == "learning_evidence_story"


def test_study_assistant_intent():
    ctx = _FakeContext(user_message="今天学什么")
    assert derive_question_lifecycle_scene(ctx) == "study_assistant"


def test_learning_support_intent():
    ctx = _FakeContext(user_message="我学不动了")
    assert derive_question_lifecycle_scene(ctx) == "learning_support"


def test_empty_message_returns_none():
    ctx = _FakeContext(user_message="")
    assert derive_question_lifecycle_scene(ctx) is None


def test_unrelated_chat_returns_none():
    ctx = _FakeContext(user_message="你好")
    assert derive_question_lifecycle_scene(ctx) is None


def test_topic_qualified_real_exam_review_returns_question_review():
    """Topic words between "一道" and "真题" still mean a real-question review."""
    ctx = _FakeContext(user_message="分析一道验槽方法真题")
    assert derive_question_lifecycle_scene(ctx) == "question_review"


def test_scene_derivation_import_does_not_require_skill_loader_dependency():
    """Pure scene routing must not import TutorBot's optional skill loader."""
    code = textwrap.dedent(
        """
        import builtins
        from types import SimpleNamespace

        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.startswith("deeptutor.tutorbot.agent."):
                raise ModuleNotFoundError(name)
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from deeptutor.services.question_lifecycle_skills import derive_question_lifecycle_scene

        ctx = SimpleNamespace(user_message="分析一道验槽方法真题", metadata={})
        assert derive_question_lifecycle_scene(ctx) == "question_review"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_mixed_turn_submission_takes_priority_over_generation_intent():
    """Plan §5.1 mixed-turn priority: active-object submission always wins."""
    ctx = _FakeContext(
        user_message="B，再出 3 题",
        metadata={"question_followup_context": _mcq_followup_context()},
    )
    assert derive_question_lifecycle_scene(ctx) == "mcq_grading"


# ---------------------------------------------------------------------------
# attach_question_lifecycle_scene_to_context — idempotent metadata attach
# ---------------------------------------------------------------------------

from deeptutor.services.question_lifecycle_skills import (
    attach_question_lifecycle_scene_to_context,
)


def test_attach_writes_scene_and_skill_names_to_metadata():
    ctx = _FakeContext(user_message="再出 3 题")
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "practice_generation"
    assert ctx.metadata["question_lifecycle_scene"] == "practice_generation"
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]


def test_attach_honors_existing_orchestrator_decision():
    """Plan §5.1: if scene already set by upstream, do not overwrite."""
    ctx = _FakeContext(
        user_message="再出 3 题",
        metadata={"question_lifecycle_scene": "study_assistant"},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene == "study_assistant"
    assert ctx.metadata["question_lifecycle_scene"] == "study_assistant"
    # skill_names projection still updates to match the scene that won
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-study-assistant",
    ]


def test_attach_honors_explicit_none_from_upstream():
    """Upstream may set scene=None to mean 'definitely chat fallback'."""
    ctx = _FakeContext(
        user_message="再出 3 题",
        metadata={"question_lifecycle_scene": None},
    )
    scene = attach_question_lifecycle_scene_to_context(ctx)
    assert scene is None
    assert ctx.metadata["question_lifecycle_scene"] is None
    assert ctx.metadata["question_lifecycle_skill_names"] == []


def test_attach_with_no_metadata_attribute_returns_none():
    class NoMeta:
        user_message = "再出 3 题"
    assert attach_question_lifecycle_scene_to_context(NoMeta()) is None


def test_attach_with_unknown_scene_writes_empty_skill_names():
    """Per plan §6.5 v2-5: low-confidence chat fallback writes scene=None, [] skills."""
    ctx = _FakeContext(user_message="你好世界")
    attach_question_lifecycle_scene_to_context(ctx)
    assert ctx.metadata["question_lifecycle_scene"] is None
    assert ctx.metadata["question_lifecycle_skill_names"] == []
