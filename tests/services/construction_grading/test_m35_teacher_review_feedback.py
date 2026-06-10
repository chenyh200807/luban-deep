from deeptutor.services.construction_grading.compiler_feedback import (
    work_order_from_teacher_override,
)


def test_teacher_override_becomes_compiler_candidate_not_release_truth():
    work_order = work_order_from_teacher_override(
        {
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_id": "Q1-NA::P2",
            "override_type": "miss_should_be_partial",
            "teacher_evidence": "学生写到组织专家但主体不完整，应部分给分",
            "source_ref_ids": ["exam_2026#p2"],
        }
    )

    assert work_order["namespace"] == "luban_compiler_candidate"
    assert work_order["kind"] == "work_order"
    assert work_order["origin"] == "m35_teacher_review"
    assert work_order["promote_to_release"] is False
    assert work_order["is_release_truth"] is False
    assert work_order["payload"]["work_order_type"] == "teacher_override_review"
    assert work_order["payload"]["promote_to_release"] is False
    assert work_order["payload"]["runtime_usable_as_truth"] is False
    assert work_order["payload"]["question_id"] == "Q1-NA"


def test_teacher_override_preserves_source_refs_and_review_payload():
    work_order = work_order_from_teacher_override(
        {
            "question_id": "Q2-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_id": "Q2-NA::P1",
            "override_type": "partial_should_be_hit",
            "teacher_evidence": "关键主体和动作均命中。",
            "source_ref_ids": ("exam_2026#p1", "textbook#c1"),
        }
    )

    assert work_order["payload"]["source_ref_ids"] == ["exam_2026#p1", "textbook#c1"]
    assert work_order["payload"]["teacher_evidence"] == "关键主体和动作均命中。"
    assert work_order["next_action"] == "route_to_llm_assisted_compiler_then_deterministic_release_gate"
