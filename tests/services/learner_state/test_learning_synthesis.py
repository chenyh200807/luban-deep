from __future__ import annotations

from deeptutor.services.learner_state.learning_synthesis import (
    find_concept_evidence,
    find_next_training_targets,
    project_learning_graph,
    render_learning_truth_summary_md,
    synthesize_learning_truth,
)
from deeptutor.services.learner_state.service import LearnerStateEvent


def _learning_event(
    event_id: str,
    *,
    concept_id: str = "1A432000",
    question_id: str = "case_001",
    rubric_item_id: str = "r1",
    error_code: str = "E02",
    observed_at: str = "2026-05-18T10:00:00+08:00",
    improved: bool = False,
    memory_kind: str = "learning_evidence",
    source_feature: str = "construction_grading",
    event_type: str = "learning_evidence",
    quality: dict | None = None,
) -> LearnerStateEvent:
    payload = {
        "event_type": event_type,
        "turn_id": f"turn_{event_id}",
        "question_id": question_id,
        "question_type": "case",
        "score_awarded": 1.0 if improved else 0.0,
        "max_score": 1.0,
        "grading_mode": "projected_rubric",
        "rubric_items": [
            {
                "rubric_item_id": rubric_item_id,
                "criterion": "专家论证程序",
                "status": "full" if improved else "miss",
            }
        ],
        "error_events": [] if improved else [
            {
                "error_code": error_code,
                "concept_tag": concept_id,
                "rubric_item_id": rubric_item_id,
                "diagnosis": "漏写专家论证程序。",
            }
        ],
        "next_training_signal": {
            "concept": concept_id,
            "focus": "专家论证程序",
            "mode": "case_repair",
        },
        "quality": quality or {"evidence_level": "L0_observed", "writeback_eligible": True},
        "typed_edges": [
            {
                "edge_type": "submission_missed_rubric_item",
                "from": {"type": "submission", "id": f"turn_{event_id}"},
                "to": {"type": "rubric_item", "id": f"{question_id}:{rubric_item_id}"},
                "source_feature": "construction_grading",
                "confidence": 0.8,
            },
            {
                "edge_type": "error_points_to_training",
                "from": {"type": "error", "id": f"{concept_id}:{error_code}"},
                "to": {"type": "next_training", "id": f"{concept_id}:{error_code}:case_repair"},
                "source_feature": "construction_grading",
                "confidence": 0.8,
            },
        ],
    }
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature=source_feature,
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind=memory_kind,
        dedupe_key=event_id,
        created_at=observed_at,
        payload_json=payload,
    )


def _manual_correction(event_id: str = "fix1") -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="manual_correction",
        source_id="teacher_fix_001",
        source_bot_id=None,
        memory_kind="learning_correction",
        dedupe_key=event_id,
        created_at="2026-05-18T13:00:00+08:00",
        payload_json={
            "event_type": "manual_correction",
            "concept_id": "1A432000",
            "error_code": "E02",
            "correction": "这次不是程序链条问题，而是责任主体表达不完整。",
            "supersedes_event_ids": ["evt1", "evt2"],
        },
    )


def test_assessment_testset_learning_evidence_is_consumed_by_synthesis() -> None:
    projection = synthesize_learning_truth([
        _learning_event(
            "assessment_evt1",
            source_feature="assessment_testset",
            question_id="assessment_q1",
            error_code="M01",
        )
    ])

    assert projection["synthesis_run"]["input_event_count"] == 1
    assert projection["weak_points"] == []
    assert projection["observed_candidates"][0]["error_code"] == "M01"
    assert projection["observed_candidates"][0]["supporting_event_ids"] == ["assessment_evt1"]
    assert "error:1A432000:M01" in projection["compiled_objects"]


def _manual_confirmation(event_id: str = "confirm1") -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="manual_correction",
        source_id="teacher_confirm_001",
        source_bot_id=None,
        memory_kind="learning_correction",
        dedupe_key=event_id,
        created_at="2026-05-18T13:00:00+08:00",
        payload_json={
            "event_type": "manual_correction",
            "action": "confirm",
            "concept_id": "1A432000",
            "error_code": "E02",
            "correction": "老师确认该学生确实反复漏写专家论证程序。",
        },
    )


def test_synthesis_keeps_single_observation_out_of_stable_truth() -> None:
    projection = synthesize_learning_truth([_learning_event("evt1")])

    assert projection["weak_points"] == []
    assert projection["observed_candidates"][0]["evidence_level"] == "L0_observed"
    assert projection["observed_candidates"][0]["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert projection["compiled_objects"]["concept:1A432000"]["evidence_level"] == "L0_observed"


def test_synthesis_promotes_repeated_error_to_l1() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9"),
    ])

    weak = projection["weak_points"][0]
    assert weak["concept_id"] == "1A432000"
    assert weak["error_code"] == "E02"
    assert weak["evidence_level"] == "L1_repeated"
    assert weak["memory_lifecycle_stage"] == "stable_learner_claim"
    assert weak["supporting_event_ids"] == ["evt1", "evt2"]


def test_synthesis_projects_trusted_ai_adjudication_from_supporting_evidence() -> None:
    quality = {
        "evidence_level": "L0_observed",
        "writeback_eligible": True,
        "trusted_adjudication": {
            "source": "llm_jury",
            "confidence": 0.91,
            "conflict_status": "resolved",
            "requires_human": False,
        },
    }

    projection = synthesize_learning_truth([
        _learning_event("evt1", quality=quality),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9", quality=quality),
    ])

    trusted = projection["synthesis_run"]["trusted_adjudication"]
    assert trusted["source"] == "llm_jury"
    assert trusted["confidence"] == 0.91
    assert trusted["conflict_status"] == "resolved"
    assert trusted["requires_human"] is False


def test_synthesis_promotes_single_certified_policy_evidence_to_l2() -> None:
    quality = {
        "evidence_level": "L2_confirmed",
        "writeback_eligible": True,
        "stable_truth_eligible": True,
        "trusted_adjudication": {
            "source": "certified_grading_policy",
            "confidence": 0.93,
            "conflict_status": "resolved",
            "requires_human": False,
            "policy_id": "policy-case-v1",
            "rubric_hash": "sha256:rubric",
            "grader_version": "rubric-grader-v1",
        },
    }

    projection = synthesize_learning_truth([
        _learning_event("evt1", quality=quality),
    ])

    weak = projection["weak_points"][0]
    assert weak["evidence_level"] == "L2_confirmed"
    assert weak["memory_lifecycle_stage"] == "stable_learner_claim"
    assert weak["supporting_event_ids"] == ["evt1"]
    trusted = projection["synthesis_run"]["trusted_adjudication"]
    assert trusted["source"] == "certified_grading_policy"
    assert trusted["confidence"] == 0.93
    assert trusted["requires_human"] is False


def test_synthesis_outputs_p0_claim_lifecycle_states() -> None:
    observed_projection = synthesize_learning_truth([_learning_event("evt1")])
    repeated_projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9"),
    ])
    confirmed_projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _manual_confirmation(),
    ])
    stale_projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9"),
        _learning_event("evt3", improved=True, observed_at="2026-05-18T14:00:00+08:00"),
    ])
    superseded_projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9"),
        _manual_correction(),
    ])

    assert observed_projection["observed_candidates"][0]["claim_status"] == "observed"
    assert observed_projection["observed_candidates"][0]["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert repeated_projection["weak_points"][0]["claim_status"] == "repeated"
    assert repeated_projection["weak_points"][0]["memory_lifecycle_stage"] == "stable_learner_claim"
    assert confirmed_projection["weak_points"][0]["claim_status"] == "confirmed"
    assert confirmed_projection["weak_points"][0]["memory_lifecycle_stage"] == "stable_learner_claim"
    assert stale_projection["stale_claims"][0]["claim_status"] == "stale"
    assert superseded_projection["compiled_objects"]["error:1A432000:E02"]["claim_status"] == "superseded"
    assert repeated_projection["weak_points"][0]["lifecycle"]["status"] == "repeated"


def test_teacher_final_single_error_promotes_to_confirmed_claim() -> None:
    event = _learning_event(
        "teacher_final_evt",
        quality={
            "evidence_level": "L0_observed",
            "writeback_eligible": True,
            "teacher_reviewed": True,
            "teacher_review_authority": "teacher_final_grading_result",
        },
    )
    event.payload_json["next_training_signal"]["teacher_final_grading_result"] = {
        "teacher_reviewed": True,
        "points": [{"point_id": "r1", "mastery_eligible": False}],
    }

    projection = synthesize_learning_truth([event])

    assert projection["observed_candidates"] == []
    weak = projection["weak_points"][0]
    assert weak["concept_id"] == "1A432000"
    assert weak["error_code"] == "E02"
    assert weak["evidence_level"] == "L2_confirmed"
    assert weak["claim_status"] == "confirmed"
    assert weak["lifecycle"]["status"] == "confirmed"


def test_real_retest_improvement_decays_teacher_final_confirmed_claim() -> None:
    teacher_final = _learning_event(
        "teacher_final_evt",
        quality={
            "evidence_level": "L0_observed",
            "writeback_eligible": True,
            "teacher_reviewed": True,
            "teacher_review_authority": "teacher_final_grading_result",
        },
    )
    teacher_final.payload_json["next_training_signal"]["teacher_final_grading_result"] = {
        "teacher_reviewed": True,
        "points": [{"point_id": "r1", "mastery_eligible": False}],
    }
    real_retest = _learning_event(
        "real_retest_pass",
        improved=True,
        observed_at="2026-05-18T14:00:00+08:00",
        quality={
            "evidence_level": "L2_real_retest",
            "writeback_eligible": True,
            "retest_happened": True,
            "retest_authority": "real_student_retest",
        },
    )
    real_retest.payload_json["claim_promotion_allowed"] = True

    projection = synthesize_learning_truth([teacher_final, real_retest])

    assert projection["weak_points"] == []
    assert projection["improvement_signals"][0]["event_id"] == "real_retest_pass"
    assert projection["stale_claims"][0]["claim_status"] == "stale"
    assert projection["compiled_objects"]["error:1A432000:E02"]["decay_state"] == "improving"


def test_synthesis_expands_all_errors_in_event() -> None:
    event1 = _learning_event("evt1")
    event1.payload_json["error_events"].append({
        "error_code": "E03",
        "concept_tag": "1A432000",
        "rubric_item_id": "r2",
        "diagnosis": "责任主体表达不完整。",
    })
    event2 = _learning_event("evt2", question_id="case_002")
    event2.payload_json["error_events"].append({
        "error_code": "E03",
        "concept_tag": "1A432000",
        "rubric_item_id": "r8",
        "diagnosis": "责任主体表达不完整。",
    })

    projection = synthesize_learning_truth([event1, event2])

    weak_codes = {item["error_code"] for item in projection["weak_points"]}
    assert {"E02", "E03"}.issubset(weak_codes)
    assert "error:1A432000:E03" in projection["compiled_objects"]


def test_concept_compiled_truth_summarizes_multiple_errors() -> None:
    event1 = _learning_event("evt1")
    event1.payload_json["error_events"].append({
        "error_code": "E03",
        "concept_tag": "1A432000",
        "rubric_item_id": "r2",
        "diagnosis": "责任主体表达不完整。",
    })
    event2 = _learning_event("evt2", question_id="case_002")
    event2.payload_json["error_events"].append({
        "error_code": "E03",
        "concept_tag": "1A432000",
        "rubric_item_id": "r8",
        "diagnosis": "责任主体表达不完整。",
    })

    projection = synthesize_learning_truth([event1, event2])
    evidence = find_concept_evidence(projection, concept_id="1A432000")

    assert "E02" in evidence["current_truth"]
    assert "E03" in evidence["current_truth"]
    assert "error:1A432000:E02" in projection["compiled_objects"]
    assert "error:1A432000:E03" in projection["compiled_objects"]


def test_synthesis_builds_object_level_compiled_truth() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1", question_id="case_001", rubric_item_id="r1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r9"),
    ])

    concept = projection["compiled_objects"]["concept:1A432000"]
    assert concept["object_type"] == "concept"
    assert concept["evidence_level"] == "L1_repeated"
    assert concept["supporting_event_ids"] == ["evt1", "evt2"]
    assert concept["timeline_refs"][0]["event_id"] == "evt1"

    error = projection["compiled_objects"]["error:1A432000:E02"]
    assert error["supporting_event_ids"] == ["evt1", "evt2"]
    assert "question:case_001" in projection["compiled_objects"]
    assert "rubric_item:case_001:r1" in projection["compiled_objects"]


def test_synthesis_marks_improvement_signal_and_decays_claim() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2"),
        _learning_event("evt3", improved=True, observed_at="2026-05-18T14:00:00+08:00"),
    ])

    assert projection["improvement_signals"][0]["concept_id"] == "1A432000"
    assert projection["stale_claims"][0]["reason"] == "later_training_improved"
    assert projection["compiled_objects"]["concept:1A432000"]["decay_state"] == "improving"
    assert projection["weak_points"] == []


def test_synthesis_decays_only_the_improved_error_object() -> None:
    projection = synthesize_learning_truth([
        _learning_event("e02_evt1", error_code="E02", question_id="case_001", rubric_item_id="r1"),
        _learning_event("e02_evt2", error_code="E02", question_id="case_002", rubric_item_id="r2"),
        _learning_event("e04_evt1", error_code="E04", question_id="case_003", rubric_item_id="r3"),
        _learning_event("e04_evt2", error_code="E04", question_id="case_004", rubric_item_id="r4"),
        _learning_event(
            "improve_e02",
            improved=True,
            error_code="E02",
            observed_at="2026-05-18T14:00:00+08:00",
        ),
    ])

    weak_codes = {item["error_code"] for item in projection["weak_points"]}
    stale_codes = {item["error_code"] for item in projection["stale_claims"]}

    assert "E02" not in weak_codes
    assert "E04" in weak_codes
    assert stale_codes == {"E02"}
    assert projection["compiled_objects"]["error:1A432000:E02"]["decay_state"] == "improving"
    assert projection["compiled_objects"]["error:1A432000:E04"]["decay_state"] == "active"


def test_concept_only_improvement_signal_does_not_clear_specific_weak_points() -> None:
    improvement = _learning_event(
        "concept_success",
        improved=True,
        observed_at="2026-05-18T14:00:00+08:00",
    )
    improvement.payload_json["typed_edges"] = []

    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002", rubric_item_id="r2"),
        improvement,
    ])

    assert projection["improvement_signals"][0]["concept_id"] == "1A432000"
    assert projection["improvement_signals"][0]["error_code"] == ""
    assert projection["weak_points"][0]["error_code"] == "E02"
    assert projection["compiled_objects"]["error:1A432000:E02"]["decay_state"] == "active"
    assert projection["stale_claims"] == []


def test_project_learning_graph_reuses_typed_edges_and_adds_metadata() -> None:
    graph = project_learning_graph([_learning_event("evt1")])

    assert graph["schema_version"] == 1
    assert graph["edges"][0]["evidence_event_id"] == "evt1"
    assert graph["edges"][0]["observed_at"] == "2026-05-18T10:00:00+08:00"
    assert graph["edges"][0]["edge_type"] == "submission_missed_rubric_item"
    assert graph["edges"][0]["source_feature"] == "construction_grading"


def test_project_learning_graph_drops_invalid_edges() -> None:
    event = _learning_event("evt1")
    event.payload_json["typed_edges"].extend([
        {
            "edge_type": "unknown_edge",
            "from": {"type": "question", "id": "case_001"},
            "to": {"type": "concept", "id": "1A432000"},
            "source_feature": "construction_grading",
            "confidence": 0.9,
        },
        {
            "edge_type": "question_tests_concept",
            "from": {"type": "question", "id": ""},
            "to": {"type": "concept", "id": "1A432000"},
            "source_feature": "construction_grading",
            "confidence": 0.9,
        },
        {
            "edge_type": "question_tests_concept",
            "from": {"type": "question", "id": "case_001"},
            "to": {"type": "concept", "id": "1A432000"},
            "source_feature": "construction_grading",
            "confidence": 2,
        },
    ])

    graph = project_learning_graph([event])

    assert all(edge["edge_type"] != "unknown_edge" for edge in graph["edges"])
    assert len([gap for gap in graph["readiness_gaps"] if gap["code"] == "invalid_graph_edge"]) == 3


def test_graph_can_trace_error_to_next_training() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2", question_id="case_002"),
    ])

    targets = find_next_training_targets(projection, concept_id="1A432000", error_code="E02")

    assert targets[0]["concept_id"] == "1A432000"
    assert targets[0]["error_code"] == "E02"
    assert targets[0]["reason_event_ids"] == ["evt1", "evt2"]


def test_missing_question_id_does_not_create_question_or_concept_truth() -> None:
    projection = synthesize_learning_truth([_learning_event("evt1", question_id="")])

    assert "question:" not in "\n".join(projection["compiled_objects"])
    assert "concept:1A432000" not in projection["compiled_objects"]
    assert projection["observed_candidates"][0]["evidence_level"] == "L0_observed"


def test_rag_degraded_cap_prevents_l1_promotion() -> None:
    projection = synthesize_learning_truth([
        _learning_event(
            "evt1",
            quality={
                "evidence_level": "L0_observed",
                "writeback_eligible": True,
                "evidence_cap_reasons": ["rag_degraded"],
            },
        ),
        _learning_event(
            "evt2",
            question_id="case_002",
            quality={
                "evidence_level": "L0_observed",
                "writeback_eligible": True,
                "evidence_cap_reasons": ["rag_degraded"],
            },
        ),
    ])

    assert projection["weak_points"] == []
    assert {item["evidence_level"] for item in projection["observed_candidates"]} == {"L0_observed"}


def test_chat_only_event_is_not_learning_evidence() -> None:
    projection = synthesize_learning_truth([
        LearnerStateEvent(
            event_id="chat1",
            user_id="student_demo",
            source_feature="turn",
            source_id="session-1",
            source_bot_id=None,
            memory_kind="turn",
            dedupe_key="chat1",
            created_at="2026-05-18T10:00:00+08:00",
            payload_json={"summary": "学生说自己案例题很弱。"},
        )
    ])

    assert projection["weak_points"] == []
    assert projection["compiled_objects"] == {}


def test_conversation_synthesis_graph_edges_are_read_without_promoting_stable_truth() -> None:
    projection = synthesize_learning_truth([
        LearnerStateEvent(
            event_id="conv1",
            user_id="student_demo",
            source_feature="conversation_synthesis",
            source_id="turn_1",
            source_bot_id=None,
            memory_kind="learning_evidence",
            dedupe_key="conv1",
            created_at="2026-06-03T10:00:00+08:00",
            payload_json={
                "event_type": "learning_evidence",
                "evidence_source": "conversation_synthesis",
                "question_id": "probe_q1",
                "error_events": [
                    {
                        "concept_tag": "1A432000",
                        "error_code": "M01",
                        "diagnosis": "知识点不熟",
                    }
                ],
                "quality": {
                    "evidence_cap_reasons": ["conversation_signal_not_grading_truth"],
                    "stable_truth_eligible": False,
                },
                "typed_edges": [
                    {
                        "edge_type": "error_points_to_training",
                        "from": {"type": "error", "id": "1A432000:M01"},
                        "to": {"type": "next_training", "id": "lti_123"},
                        "source_feature": "conversation_synthesis",
                        "confidence": 0.45,
                    }
                ],
            },
        )
    ])

    assert projection["weak_points"] == []
    assert projection["typed_graph"]["edges"][0]["edge_type"] == "error_points_to_training"
    assert projection["typed_graph"]["edges"][0]["source_feature"] == "conversation_synthesis"


def test_manual_correction_supersedes_automatic_claim() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event("evt2"),
        _manual_correction(),
    ])

    error = projection["compiled_objects"]["error:1A432000:E02"]
    assert error["decay_state"] == "superseded"
    assert error["superseded_by_event_ids"] == ["fix1"]
    assert projection["synthesis_run"]["manual_override_count"] == 1
    assert projection["weak_points"] == []


def test_manual_confirmation_upgrades_claim_to_l2_confirmed() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _manual_confirmation(),
    ])

    concept = projection["compiled_objects"]["concept:1A432000"]
    assert concept["evidence_level"] == "L2_confirmed"
    assert concept["supporting_event_ids"] == ["evt1", "confirm1"]
    assert concept["timeline_refs"][-1]["event_type"] == "manual_correction"
    assert projection["synthesis_run"]["manual_override_count"] == 1
    assert projection["weak_points"][0]["evidence_level"] == "L2_confirmed"
    assert projection["weak_points"][0]["supporting_event_ids"] == ["evt1", "confirm1"]


def test_manual_confirmation_keeps_compiled_object_confidence_aligned_with_l2() -> None:
    event = _learning_event("evt1", error_code="E02")
    event.payload_json["error_events"].append({
        "error_code": "E04",
        "concept_tag": "1A432000",
        "rubric_item_id": "r4",
        "diagnosis": "措施适用边界表达不清。",
    })

    projection = synthesize_learning_truth([event, _manual_confirmation()])

    concept = projection["compiled_objects"]["concept:1A432000"]
    assert concept["evidence_level"] == "L2_confirmed"
    assert concept["confidence"] == 0.9


def test_synthesis_is_idempotent_for_same_inputs() -> None:
    events = [_learning_event("evt1"), _learning_event("evt2")]

    first = synthesize_learning_truth(events)
    second = synthesize_learning_truth(events)

    assert first["synthesis_run"]["input_event_ids_hash"] == second["synthesis_run"]["input_event_ids_hash"]
    assert first["synthesis_run"]["output_projection_hash"] == second["synthesis_run"]["output_projection_hash"]


def test_synthesis_marks_conflicting_evidence_without_overwriting_claim() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt1"),
        _learning_event(
            "evt2",
            quality={
                "evidence_level": "L0_observed",
                "writeback_eligible": True,
                "conflicting_event_ids": ["evt1"],
            },
        ),
    ])

    error = projection["compiled_objects"]["error:1A432000:E02"]
    assert error["conflicting_event_ids"] == ["evt1"]
    assert projection["synthesis_run"]["conflict_count"] == 1


def test_render_learning_truth_summary_md_is_teacher_readable() -> None:
    projection = synthesize_learning_truth([_learning_event("evt1"), _learning_event("evt2")])

    summary = render_learning_truth_summary_md(projection)

    assert "学习事实编译" in summary
    assert "1A432000" in summary
    assert "E02" in summary


def _shadow_authority_event(event_id: str) -> LearnerStateEvent:
    # A leaked shadow row written directly into learner_memory_events (should NEVER happen by
    # construction, but the read path must defensively exclude it so claims/PCP stay clean).
    ev = _learning_event(event_id)
    payload = dict(ev.payload_json)
    payload["authority"] = "best_quality_4model_shadow"
    payload["candidate_only"] = True
    return LearnerStateEvent(
        event_id=ev.event_id, user_id=ev.user_id, source_feature=ev.source_feature,
        source_id=ev.source_id, source_bot_id=ev.source_bot_id, memory_kind=ev.memory_kind,
        dedupe_key=ev.dedupe_key, created_at=ev.created_at, payload_json=payload)


def test_leaked_shadow_evidence_is_excluded_from_synthesis() -> None:
    # SAFETY NET (Step 0): even if a shadow-authority / not-writeback-eligible row somehow lands in the
    # event table, the read path must drop it — it must never become a claim / weak point / PCP input.
    proj = synthesize_learning_truth([
        _shadow_authority_event("shadow1"),
        _shadow_authority_event("shadow2"),  # would be L1_repeated stable truth if not excluded
    ])
    assert proj["weak_points"] == []
    assert proj["observed_candidates"] == []
    assert "error:1A432000:E02" not in proj["compiled_objects"]


def test_not_writeback_eligible_evidence_is_excluded_from_synthesis() -> None:
    proj = synthesize_learning_truth([
        _learning_event("ne1", quality={"evidence_level": "L0_observed", "writeback_eligible": False}),
        _learning_event("ne2", quality={"evidence_level": "L0_observed", "writeback_eligible": False}),
    ])
    assert proj["weak_points"] == []
    assert proj["observed_candidates"] == []


def test_eligible_evidence_still_consumed_after_safety_filter() -> None:
    # Regression guard: the defensive filter must NOT drop legitimate writeback_eligible evidence.
    proj = synthesize_learning_truth([_learning_event("ok1"), _learning_event("ok2")])
    assert "error:1A432000:E02" in proj["compiled_objects"]
