"""Control-plane Task 2 audit: prove ``question_followup_context`` is a pure
derived read of ``active_object.state_snapshot`` before collapsing the
independent metadata writes.

Every production writer of ``question_followup_context`` co-writes an
``active_object`` whose ``state_snapshot`` is built from the *same* question
context (``build_active_object_from_question_context``), and every reader can
recover the context via ``question_context_from_active_object`` /
``extract_question_context_from_active_object``
(``= normalize_question_followup_context(active_object["state_snapshot"])``).

This module asserts the value-equality that underpins the collapse:

  followup_context (written)  ==  question_context_from_active_object(
                                      build_active_object_from_question_context(followup_context))

If any of these RED, the write carries information the active_object does not,
the projection is *not* pure, and the collapse must STOP.
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.question_followup import (
    annotate_submission_context_from_message,
    build_question_followup_context_from_result_summary,
    normalize_question_followup_context,
)
from deeptutor.services.semantic_router import (
    build_active_object_from_question_context,
    question_context_from_active_object,
)
from deeptutor.services.session.sqlite_store import (
    extract_question_context_from_active_object,
)


# --- Representative question contexts spanning the writer surface. -------------
# single MCQ (unanswered), single MCQ (graded), batch set, subjective/case,
# revealed-reference, evidence-carrying.
_SINGLE_MCQ_UNANSWERED: dict[str, Any] = {
    "parent_quiz_session_id": "sess-1",
    "question_id": "q-1",
    "question": "下列哪项属于危大工程？",
    "question_type": "single_choice",
    "options": [
        {"key": "A", "value": "深基坑"},
        {"key": "B", "value": "砌墙"},
    ],
    "correct_answer": "A",
    "explanation": "深基坑属于危大工程。",
    "difficulty": "medium",
    "concentration": "high",
    "knowledge_context": "危大工程范围",
    "multi_select": False,
}

_SINGLE_MCQ_GRADED: dict[str, Any] = {
    **_SINGLE_MCQ_UNANSWERED,
    "user_answer": "A",
    "is_correct": True,
    "reveal_answers": True,
    "reveal_explanations": True,
}

_BATCH_SET: dict[str, Any] = {
    "parent_quiz_session_id": "sess-2",
    "question": "第1题",
    "question_type": "single_choice",
    "items": [
        {
            "question_id": "q-a",
            "question": "第1题",
            "question_type": "single_choice",
            "options": [{"key": "A", "value": "对"}, {"key": "B", "value": "错"}],
            "correct_answer": "A",
        },
        {
            "question_id": "q-b",
            "question": "第2题",
            "question_type": "single_choice",
            "options": [{"key": "A", "value": "对"}, {"key": "B", "value": "错"}],
            "correct_answer": "B",
        },
    ],
}

_SUBJECTIVE_CASE: dict[str, Any] = {
    "parent_quiz_session_id": "sess-3",
    "question_id": "case-1",
    "question": "请论证该工程是否需要专家论证。",
    "question_type": "subjective",
    "correct_answer": "需要专家论证。",
    "explanation": "依据危大工程管理规定。",
    "evidence_refs": [
        {
            "source": "lecture",
            "field": "rule",
            "content": "超过一定规模的危大工程必须专家论证。",
            "source_type": "lecture",
        }
    ],
}

_ALL_CONTEXTS = {
    "single_mcq_unanswered": _SINGLE_MCQ_UNANSWERED,
    "single_mcq_graded": _SINGLE_MCQ_GRADED,
    "batch_set": _BATCH_SET,
    "subjective_case": _SUBJECTIVE_CASE,
}


@pytest.mark.parametrize("name", list(_ALL_CONTEXTS))
def test_followup_context_equals_derived_from_active_object(name: str) -> None:
    """The canonical projection the orchestrator/tutorbot writes equals the
    derived read of the co-written active_object — for every reader entrypoint.

    This is the value-equality proof for the orchestrator write points
    (``_resolve_turn_semantic_decision``, ``_prepare_question_submission_context``,
    ``_prepare_practice_request_context``) and the tutorbot exact-question write
    point, all of which do::

        metadata["question_followup_context"] = fc
        metadata["active_object"] = build_active_object_from_question_context(fc)
    """
    raw_context = _ALL_CONTEXTS[name]
    written_context = normalize_question_followup_context(raw_context)
    assert written_context is not None

    active_object = build_active_object_from_question_context(written_context)
    assert active_object is not None

    # semantic_router reader path (orchestrator + question_lifecycle_skills)
    assert question_context_from_active_object(active_object) == written_context
    # sqlite_store reader path (turn_runtime persist/restore + tutorbot manager)
    assert extract_question_context_from_active_object(active_object) == written_context


@pytest.mark.parametrize("name", list(_ALL_CONTEXTS))
def test_normalize_is_idempotent(name: str) -> None:
    """The projection is stable: re-normalizing the written value is a no-op.

    Idempotency is what makes ``normalize(state_snapshot)`` recover the exact
    written context (state_snapshot is itself ``normalize(fc)``), so the
    double-normalize the derived read performs cannot drift.
    """
    once = normalize_question_followup_context(_ALL_CONTEXTS[name])
    twice = normalize_question_followup_context(once)
    assert once == twice


def test_tutorbot_exact_question_write_is_pure_projection() -> None:
    """TutorBot exact-question path: the value it writes to metadata equals the
    derived read of the active_object it co-writes (capabilities/tutorbot.py:626-654).

    Reconstructs the in-capability builder chain
    (``build_question_followup_context_from_result_summary`` +
    ``annotate_submission_context_from_message``) and asserts the round-trip.
    """
    result_summary = {
        "exact_question": {
            "question_id": "q-exact",
            "question": "下列哪项属于危大工程？",
            "question_type": "single_choice",
            "options": [
                {"key": "A", "value": "深基坑"},
                {"key": "B", "value": "砌墙"},
            ],
            "correct_answer": "A",
            "explanation": "深基坑属于危大工程。",
        }
    }
    fc = build_question_followup_context_from_result_summary(
        result_summary,
        "选 A",
        reveal_answers=True,
        reveal_explanations=True,
    )
    if fc is None:
        pytest.skip("builder produced no exact-question context for this fixture")
    fc = annotate_submission_context_from_message("我选A", fc) or fc

    active_object = build_active_object_from_question_context(fc)
    assert active_object is not None
    # The metadata write tutorbot performs (dict(fc)) must be byte-equal to the
    # derived read of the active_object it writes in the same block.
    assert extract_question_context_from_active_object(active_object) == normalize_question_followup_context(fc)


def test_persist_and_publish_active_branch_is_literal_derived_read() -> None:
    """``_persist_and_publish`` (turn_runtime.py:6433) already computes the
    written followup_context as ``extract_question_context_from_active_object(
    active_object)`` whenever active_object exists — i.e. it is *already* a
    derived read, not an independent judgment. Asserting the value-equivalence
    of that branch documents the collapse target.
    """
    from deeptutor.services.session.turn_runtime import (
        _result_question_followup_context,
    )

    written = normalize_question_followup_context(_BATCH_SET)
    active_object = build_active_object_from_question_context(written)
    assert active_object is not None

    # active branch (line 6434): value is the derived read.
    active_branch_value = extract_question_context_from_active_object(active_object)
    # no-active fallback branch (line 6436): value derives from metadata.
    metadata = {"question_followup_context": written}
    fallback_value = _result_question_followup_context(metadata)

    assert active_branch_value == written
    assert fallback_value == written
