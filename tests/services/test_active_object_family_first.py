"""M2: object_type 题型/非题型 family-first 分流 — single family authority.

These tests pin the M2 collapse: the question-family ("题型") membership decision is
made by ONE authority (``semantic_router.active_object_family_for_type`` /
``is_question_active_object_type``, sourced from
``active_object_builder.QUESTION_ACTIVE_OBJECT_TYPES``). Non-question objects
(open_chat_topic / guide_page / study_plan / question_lifecycle_clarification) are
short-circuited family-first rather than falling into question logic on a None backstop;
``open_world_question`` is no longer silently dropped by hand-listed
``{question_set, single_question}`` literals.
"""

from __future__ import annotations

import pytest

from deeptutor.services.active_object_builder import QUESTION_ACTIVE_OBJECT_TYPES
from deeptutor.services.semantic_router import (
    GUIDE_ACTIVE_OBJECT_TYPES,
    QUESTION_ACTIVE_OBJECT_TYPES as SR_QUESTION_ACTIVE_OBJECT_TYPES,
    SESSION_ACTIVE_OBJECT_TYPES,
    _active_object_family,
    active_object_family_for_type,
    is_question_active_object_type,
)

QUESTION_TYPES = ("single_question", "question_set", "open_world_question")
NON_QUESTION_TYPES = (
    "open_chat_topic",
    "guide_page",
    "study_plan",
    "question_lifecycle_clarification",
)


def test_single_authority_question_set_is_one_fact() -> None:
    # The question-family set has exactly ONE definition consumed everywhere; the
    # semantic_router re-export and the builder authority must not drift.
    assert QUESTION_ACTIVE_OBJECT_TYPES == SR_QUESTION_ACTIVE_OBJECT_TYPES
    assert QUESTION_ACTIVE_OBJECT_TYPES == set(QUESTION_TYPES)


@pytest.mark.parametrize("object_type", QUESTION_TYPES)
def test_question_family_types_classify_as_question(object_type: str) -> None:
    assert is_question_active_object_type(object_type) is True
    assert active_object_family_for_type(object_type) == "question"


def test_open_world_question_is_not_dropped() -> None:
    # Regression for the M2 disease: hand-listed {question_set, single_question}
    # literals silently dropped open_world_question from the question family.
    assert is_question_active_object_type("open_world_question") is True
    assert active_object_family_for_type("open_world_question") == "question"


@pytest.mark.parametrize("object_type", NON_QUESTION_TYPES)
def test_non_question_types_short_circuit(object_type: str) -> None:
    # Non-question objects must NOT enter question logic — they are short-circuited
    # family-first, not left to fall through on a None question-context backstop.
    assert is_question_active_object_type(object_type) is False
    assert active_object_family_for_type(object_type) != "question"


def test_guide_and_session_families_resolve() -> None:
    for object_type in GUIDE_ACTIVE_OBJECT_TYPES:
        assert active_object_family_for_type(object_type) == "guide"
    for object_type in SESSION_ACTIVE_OBJECT_TYPES:
        assert active_object_family_for_type(object_type) == "open_chat"


@pytest.mark.parametrize("blank", [None, "", "   ", "totally_unknown_type"])
def test_unknown_or_blank_is_not_question(blank) -> None:
    assert is_question_active_object_type(blank) is False
    assert active_object_family_for_type(blank) == ""


def test_dict_level_family_forwards_to_string_authority() -> None:
    # _active_object_family (dict-level) must agree with the string-level authority —
    # there is only ONE classification, not two.
    for object_type in QUESTION_TYPES:
        active_object = {
            "object_type": object_type,
            "object_id": "q1",
            "state_snapshot": {"question": "x", "options": {"A": "a", "B": "b"}},
        }
        assert _active_object_family(active_object) == "question"
    guide_object = {
        "object_type": "guide_page",
        "object_id": "g1",
        "state_snapshot": {"summary": "s"},
    }
    assert _active_object_family(guide_object) == "guide"


def test_counter_question_state_inputs_collapse_six_to_three() -> None:
    # before: 2 hand-listed question literal types + 4 non-question types reaching the
    # question-state path via None fall-through = 6 distinct object_types touching it.
    # after: exactly the 3 question-family types enter; all non-question short-circuit.
    universe = list(QUESTION_TYPES) + list(NON_QUESTION_TYPES)
    enters = [t for t in universe if is_question_active_object_type(t)]
    short_circuited = [t for t in universe if not is_question_active_object_type(t)]
    assert set(enters) == set(QUESTION_TYPES)
    assert len(enters) == 3
    assert set(short_circuited) == set(NON_QUESTION_TYPES)
