from __future__ import annotations

from deeptutor.capabilities.deep_question import DeepQuestionCapability

_is_unresolved_switch = DeepQuestionCapability._is_unresolved_switch_followup


def test_switch_to_new_object_with_followup_explainer_is_unresolved_switch() -> None:
    # P1-Y signature (R3-05): learner asked to return/switch to a different question
    # ("回到刚才屋面那道") but the decision degraded to a followup on the stale active
    # object. This exact combo must be detected so the turn clarifies, not answer the
    # wrong question.
    assert _is_unresolved_switch(
        {
            "relation_to_active_object": "switch_to_new_object",
            "next_action": "route_to_followup_explainer",
        }
    )


def test_legit_followup_on_active_object_is_not_unresolved_switch() -> None:
    # "为什么A错" — a real followup on the active object. Must NOT be diverted.
    assert not _is_unresolved_switch(
        {
            "relation_to_active_object": "ask_about_active_object",
            "next_action": "route_to_followup_explainer",
        }
    )


def test_answer_or_revise_on_active_object_is_not_unresolved_switch() -> None:
    # grading/revision paths (answer_active_object / revise_answer_on_active_object)
    # are handled by their own routing and must not be touched by the switch guard.
    for relation in ("answer_active_object", "revise_answer_on_active_object"):
        assert not _is_unresolved_switch(
            {"relation_to_active_object": relation, "next_action": "route_to_grading"}
        )


def test_switch_that_resolves_to_generation_is_not_unresolved_switch() -> None:
    # A real switch to a newly-resolved question routes to generation/grading, not a
    # followup explainer — so it is not the failed-switch signature.
    assert not _is_unresolved_switch(
        {
            "relation_to_active_object": "switch_to_new_object",
            "next_action": "route_to_generation",
        }
    )


def test_none_or_malformed_decision_is_not_unresolved_switch() -> None:
    assert not _is_unresolved_switch(None)
    assert not _is_unresolved_switch({})
    assert not _is_unresolved_switch({"next_action": "route_to_followup_explainer"})
