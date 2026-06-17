"""M25-A: unified GradingPacket lane router — lane selection + authority boundary."""
from __future__ import annotations

from deeptutor.services.construction_grading import grading_packet_builder as B


def _ctx(status="resolved", question_type="single_choice", **extra):
    base = {"status": status, "question_id": "qid", "question_type": question_type,
            "answer_key": "A", "source_refs": [{"ref": "s"}]}
    base.update(extra)
    return base


def test_objective_lane_llm_cannot_decide_correctness():
    p = B.build_grading_packet(_ctx(question_type="multiple_choice"), selected_option="AB")
    assert p["lane"] == B.LANE_OBJECTIVE
    assert p["grading_authority"] == "answer_key"
    assert p["llm_may_decide_correctness"] is False
    assert p["answer_key"] == "A"
    assert p["selected_option"] == "AB"


def test_true_false_routes_objective():
    p = B.build_grading_packet(_ctx(question_type="true_false"))
    assert p["lane"] == B.LANE_OBJECTIVE


def test_case_lane_not_polluted_by_objective_rules():
    p = B.build_grading_packet(_ctx(question_type="case_question"), student_answer="ans")
    assert p["lane"] == B.LANE_CASE
    assert p["objective_rules_applied"] is False
    assert "answer_key" not in p  # case lane has no objective answer_key authority
    assert p["grading_authority"].startswith("rubric")


def test_calculation_lane():
    p = B.build_grading_packet(_ctx(question_type="calculation"), student_answer="42")
    assert p["lane"] == B.LANE_CALCULATION
    assert p["grading_authority"] == "machine_checkable_spec"


def test_retrieval_lane_no_grading_decision():
    p = B.build_grading_packet(_ctx(question_type="retrieval"))
    assert p["lane"] == B.LANE_RETRIEVAL
    assert p["grading_decision"] is None


def test_unresolved_falls_open_to_open_world_no_official_answer():
    p = B.build_grading_packet(_ctx(status="unresolved", question_type=""), student_answer="ans")
    assert p["lane"] == B.LANE_OPEN_WORLD
    assert p["teaching"] is True
    assert p["label"] == "unverified_diagnostic"
    assert p["official_answer_claimed"] is False
    assert p["auto_score"] is False
    assert p["candidate_work_order"]["promote_to_release"] is False


def test_unknown_resolved_type_defaults_to_retrieval_not_objective():
    # a resolved identity with an unclassified type must NOT fabricate an objective verdict
    p = B.build_grading_packet(_ctx(question_type="weird_new_type"))
    assert p["lane"] == B.LANE_RETRIEVAL
