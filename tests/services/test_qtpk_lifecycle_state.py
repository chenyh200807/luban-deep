"""M1: explicit question lifecycle_state — READ-ONLY derivation.

Shadow-consistency validation (offline): asserts the explicit lifecycle_state
derived by QTPK matches the implicit object_type/per-item classification on
representative contexts. Zero behavior — purely a derived diagnostic anchor for
M2/M3. Verifies the god-object red line (no sixth fact): per-item state is READ
from items[].{user_answer, is_correct, construction_grading_result}.
"""

from __future__ import annotations

from deeptutor.services.active_object_builder import build_active_object_from_question_context
from deeptutor.services.question_turn_policy import (
    LIFECYCLE_ATTEMPTED,
    LIFECYCLE_GRADED,
    LIFECYCLE_PRESENTED,
    TurnPolicyDecision,
    derive_question_lifecycle_state,
)


def _ao(question_context: dict, *, object_type: str | None = None) -> dict:
    ao = build_active_object_from_question_context(question_context)
    assert ao is not None
    if object_type is not None:
        ao = dict(ao)
        ao["object_type"] = object_type
        snap = dict(ao.get("state_snapshot") or {})
        ao["state_snapshot"] = snap
    return ao


# --------------------------------------------------------------- single question

def test_single_question_presented_when_no_answer() -> None:
    ao = _ao({"question_id": "q1", "question": "Q?", "question_type": "choice",
              "options": {"A": "x", "B": "y"}})
    st = derive_question_lifecycle_state(active_object=ao)
    assert st is not None
    assert st["object_type"] == "single_question"
    assert st["state"] == LIFECYCLE_PRESENTED
    assert st["graded_pending"] is False
    assert st["items"][0]["state"] == LIFECYCLE_PRESENTED


def test_single_question_attempted_when_answer_no_verdict() -> None:
    ao = _ao({"question_id": "q1", "question": "Q?", "question_type": "choice",
              "options": {"A": "x", "B": "y"}, "user_answer": "A", "is_correct": None})
    st = derive_question_lifecycle_state(active_object=ao)
    assert st["state"] == LIFECYCLE_ATTEMPTED
    assert st["graded_pending"] is False  # single (not open_world) → no graded-pending


def test_single_question_graded_when_verdict() -> None:
    for verdict in (True, False):
        ao = _ao({"question_id": "q1", "question": "Q?", "question_type": "choice",
                  "options": {"A": "x", "B": "y"}, "user_answer": "A", "is_correct": verdict})
        st = derive_question_lifecycle_state(active_object=ao)
        assert st["state"] == LIFECYCLE_GRADED


# --------------------------------------------------------------- open world

def test_open_world_graded_pending_substate() -> None:
    ao = _ao({"question_id": "q1", "question": "论述?", "question_type": "essay",
              "user_answer": "我的作答", "is_correct": None}, object_type="open_world_question")
    st = derive_question_lifecycle_state(active_object=ao)
    assert st["object_type"] == "open_world_question"
    assert st["state"] == LIFECYCLE_ATTEMPTED
    assert st["graded_pending"] is True  # open_world attempt awaiting RAG verdict


def test_open_world_graded_when_grading_result_present() -> None:
    ao = _ao({"question_id": "q1", "question": "论述?", "question_type": "essay",
              "user_answer": "我的作答", "is_correct": None,
              "construction_grading_result": {"score_awarded": 6.0}},
             object_type="open_world_question")
    st = derive_question_lifecycle_state(active_object=ao)
    assert st["state"] == LIFECYCLE_GRADED
    assert st["graded_pending"] is False


# --------------------------------------------------------------- question set (per-item)

def test_question_set_per_item_mixed_progress() -> None:
    # E8 shape: item1 GRADED, item2 未答 — a single flat state cannot represent this.
    ao = _ao({
        "question_id": "set",
        "question": "题组",
        "items": [
            {"question_id": "q1", "question": "第一题", "question_type": "choice",
             "options": {"A": "x", "B": "y"}, "user_answer": "A", "is_correct": True},
            {"question_id": "q2", "question": "第二题", "question_type": "choice",
             "options": {"A": "x", "B": "y"}},
        ],
    })
    st = derive_question_lifecycle_state(active_object=ao)
    assert st["object_type"] == "question_set"
    assert st["state"] == LIFECYCLE_ATTEMPTED  # summary: mixed
    by_id = {it["question_id"]: it["state"] for it in st["items"]}
    assert by_id["q1"] == LIFECYCLE_GRADED
    assert by_id["q2"] == LIFECYCLE_PRESENTED


def test_question_set_all_graded_summary() -> None:
    ao = _ao({
        "question_id": "set", "question": "题组",
        "items": [
            {"question_id": "q1", "question": "第一题", "question_type": "choice",
             "options": {"A": "x", "B": "y"}, "user_answer": "A", "is_correct": True},
            {"question_id": "q2", "question": "第二题", "question_type": "choice",
             "options": {"A": "x", "B": "y"}, "user_answer": "B", "is_correct": False},
        ],
    })
    st = derive_question_lifecycle_state(active_object=ao)
    assert st["state"] == LIFECYCLE_GRADED


# --------------------------------------------------------------- non-question → None

def test_non_question_objects_have_no_lifecycle() -> None:
    for object_type in ("open_chat_topic", "guide_page", "study_plan", "question_lifecycle_clarification"):
        ao = {"object_type": object_type, "object_id": f"{object_type}:x",
              "state_snapshot": {"topic": "闲聊"}}
        assert derive_question_lifecycle_state(active_object=ao) is None, object_type


def test_no_active_object_returns_none() -> None:
    assert derive_question_lifecycle_state(active_object=None) is None
    assert derive_question_lifecycle_state(active_object={}) is None


# --------------------------------------------------------------- suspended (I2)

def test_suspended_stack_surfaced_for_identity_invariant() -> None:
    ao = _ao({"question_id": "q1", "question": "Q?", "question_type": "choice",
              "options": {"A": "x", "B": "y"}})
    stack = [{"object_type": "question_set", "object_id": "set:Q9"}]
    st = derive_question_lifecycle_state(active_object=ao, suspended_object_stack=stack)
    assert st["suspended"] == [{"object_type": "question_set", "object_id": "set:Q9"}]


# --------------------------------------------------------------- property forwards

def test_turn_policy_decision_property_forwards() -> None:
    ao = _ao({"question_id": "q1", "question": "Q?", "question_type": "choice",
              "options": {"A": "x", "B": "y"}, "user_answer": "A", "is_correct": True})
    decision = TurnPolicyDecision(active_object=ao)
    assert decision.lifecycle_state == derive_question_lifecycle_state(active_object=ao)
    assert decision.lifecycle_state["state"] == LIFECYCLE_GRADED


def test_empty_decision_property_is_none() -> None:
    assert TurnPolicyDecision().lifecycle_state is None
