from __future__ import annotations

from deeptutor.capabilities.deep_question import DeepQuestionCapability

_parse = DeepQuestionCapability._mcq_grading_context_from_full_submission


def test_pasted_single_choice_parsed_on_learner_surface() -> None:
    ctx = _parse("某工程屋面坡度最小值（）。A.5% B.2% C.3% D.1%。我选A")
    assert ctx is not None
    assert ctx["question_type"] == "choice"
    assert ctx["options"] == {"A": "5%", "B": "2%", "C": "3%", "D": "1%"}  # learner surface
    assert ctx["user_answer"] == "A"
    assert ctx["correct_answer"] == ""  # open-world adjudication, no bank letter leaked


def test_pasted_multi_choice_extracts_all_selected() -> None:
    ctx = _parse("正确的有：A.导管法 B.槽段8到10m C.导墙 D.墙底注浆。我选ACD")
    assert ctx is not None
    assert ctx["user_answer"] == "ACD"


def test_value_only_answer_maps_to_learner_letter() -> None:
    # "我选5%" (value, not letter) -> deterministically mapped to the learner's A.
    ctx = _parse("坡度最小值（）。A.5% B.2% C.3% D.1%。我选5%")
    assert ctx is not None
    assert ctx["user_answer"] == "A"


def test_non_mcq_and_chat_return_none() -> None:
    assert _parse("介绍一下流水施工") is None
    assert _parse("今天好热啊") is None
    assert _parse("") is None


def test_canonical_turn_decision_missing_predicate() -> None:
    # Context-Continuity task #12 step 2: observation predicate for "deep_question reached
    # without the orchestrator's canonical turn_semantic_decision" (the fabricated-fallback
    # path the migration removes). Zero behavior change — observation only.
    missing = DeepQuestionCapability._canonical_turn_decision_missing
    assert missing({}) is True  # no key
    assert missing({"turn_semantic_decision": {}}) is True  # empty / falsy
    assert missing(None) is False  # non-dict → not applicable
    assert (
        missing(
            {
                "turn_semantic_decision": {
                    "relation_to_active_object": "answer_active_object",
                    "next_action": "route_to_grading",
                }
            }
        )
        is False  # canonical decision present
    )
