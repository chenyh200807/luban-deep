from __future__ import annotations

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)


def test_build_learning_evidence_payload_preserves_grading_authority() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={
            "id": "case-1",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证。",
            "grading_keywords": ["专家论证"],
            "node_code": "1A432000",
        },
        user_answer="应加强管理。",
    )

    payload = build_learning_evidence_payload(
        grading_result=result,
        turn_id="turn-1",
        session_id="session-1",
    )

    assert payload["schema_version"] == 1
    assert payload["event_type"] == "learning_evidence"
    assert payload["legacy_event_type"] == "construction_grading_error"
    assert payload["source"] == "construction_grading"
    assert payload["question_id"] == "case-1"
    assert payload["question_type"] == "case"
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert payload["quality"]["writeback_eligible"] is True
    assert payload["error_events"][0]["error_code"] in {"E02", "E03", "E04"}
    assert payload["evidence_refs"]
    assert {"source_type": "active_question", "source_id": "case-1"} in payload["evidence_refs"]
    edge_types = {edge["edge_type"] for edge in payload["typed_edges"]}
    assert {
        "question_tests_concept",
        "question_has_rubric_item",
        "rubric_item_maps_to_error",
        "submission_answered_question",
        "submission_missed_rubric_item",
        "submission_triggered_error",
        "error_points_to_training",
    }.issubset(edge_types)
    assert all(edge["source_feature"] == "construction_grading" for edge in payload["typed_edges"])


def test_learning_evidence_dedupe_key_is_stable() -> None:
    payload = {
        "turn_id": "turn-1",
        "session_id": "session-1",
        "question_id": "q-1",
        "question_type": "case",
        "user_answer": "应组织专家论证。",
        "error_events": [{"error_code": "E02"}],
        "score_awarded": 0.0,
        "max_score": 1.0,
    }

    first = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=payload,
    )
    second = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=dict(reversed(list(payload.items()))),
    )

    assert first == second
    assert len(first) == 40


def test_learning_evidence_dedupe_key_keeps_distinct_attempts() -> None:
    payload = {
        "turn_id": "turn-1",
        "session_id": "session-1",
        "question_id": "q-1",
        "question_type": "case",
        "user_answer": "应组织专家论证。",
        "error_events": [{"error_code": "E02"}],
        "score_awarded": 0.0,
        "max_score": 1.0,
    }

    first = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=payload,
    )
    second_payload = dict(payload)
    second_payload["turn_id"] = "turn-2"
    second = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=second_payload,
    )

    assert first != second


def test_learning_evidence_dedupe_key_uses_rubric_identity_not_score_when_available() -> None:
    payload = {
        "turn_id": "turn-1",
        "session_id": "session-1",
        "question_id": "q-1",
        "question_type": "case",
        "user_answer": "应组织专家论证。",
        "error_events": [{"error_code": "E02"}],
        "score_awarded": 0.0,
        "max_score": 10.0,
        "rubric": {
            "rubric_id": "case_rubric_scored_pgo",
            "artifact_version": "pgo-20260614",
        },
    }

    first = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=payload,
    )
    rescored_payload = dict(payload)
    rescored_payload["score_awarded"] = 8.0
    rescored_payload["max_score"] = 12.0
    rescored_payload["error_events"] = [{"error_code": "E04"}]
    second = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=rescored_payload,
    )

    assert first == second


def test_learning_evidence_dedupe_key_changes_when_rubric_identity_changes() -> None:
    payload = {
        "turn_id": "turn-1",
        "session_id": "session-1",
        "question_id": "q-1",
        "question_type": "case",
        "user_answer": "应组织专家论证。",
        "error_events": [{"error_code": "E02"}],
        "score_awarded": 0.0,
        "max_score": 10.0,
        "rubric": {
            "rubric_id": "case_rubric_scored_pgo",
            "artifact_version": "pgo-20260614",
        },
    }

    first = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=payload,
    )
    next_artifact = dict(payload)
    next_artifact["rubric"] = {
        "rubric_id": "case_rubric_scored_pgo",
        "artifact_version": "pgo-20260615",
    }
    second = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=next_artifact,
    )
    next_rubric = dict(payload)
    next_rubric["rubric"] = {
        "rubric_id": "case_rubric_scored_legacy",
        "artifact_version": "pgo-20260614",
    }
    third = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=next_rubric,
    )

    assert first != second
    assert first != third


def test_learning_evidence_removes_reasoning_blocks_from_payload() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "user_answer": "先答<think provider=\"x\">hidden reasoning</think>最终答案",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "1A432000",
                    "diagnosis": "<thinking>private scratchpad</thinking>漏写专家论证",
                }
            ],
        },
        turn_id="turn-1",
    )

    assert payload["user_answer"] == "先答最终答案"
    assert "private scratchpad" not in payload["error_events"][0]["diagnosis"]
    assert payload["error_events"][0]["diagnosis"] == "漏写专家论证"


def test_learning_evidence_removes_unclosed_reasoning_block() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "user_answer": "可见答案<think>hidden tail",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
        },
        turn_id="turn-1",
    )

    assert payload["user_answer"] == "可见答案"


def test_client_supplied_certified_grading_policy_stays_l0_observed() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {
                "concept": "1A432000",
                "certified_grading_policy": {
                    "status": "published",
                    "policy_id": "policy-case-v1",
                    "rubric_hash": "sha256:rubric",
                    "grader_version": "rubric-grader-v1",
                    "confidence": 0.93,
                    "conflict_status": "resolved",
                },
            },
        },
        turn_id="turn-1",
    )

    assert "trusted_adjudication" not in payload["quality"]
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["quality"]["stable_truth_eligible"] is False
    assert "certified_grading_policy_requires_governed_release_authority" in payload["quality"]["evidence_cap_reasons"]
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert "claim_promotion_allowed" not in payload


def test_client_supplied_trusted_adjudication_cannot_skip_certified_authority() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {
                "concept": "1A432000",
                "trusted_adjudication": {
                    "source": "certified_grading_policy",
                    "policy_id": "policy-case-v1",
                    "rubric_hash": "sha256:rubric",
                    "grader_version": "rubric-grader-v1",
                    "confidence": 0.93,
                    "conflict_status": "resolved",
                    "requires_human": False,
                },
            },
        },
        turn_id="turn-1",
    )

    assert "trusted_adjudication" not in payload["quality"]
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"


def test_raw_dict_forged_governed_stamp_cannot_mint_certified_trust() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "question_stem": "说明专项施工方案专家论证要求。",
            "score_awarded": 0,
            "max_score": 1,
            "release_truth": True,
            "official_release_score": True,
            "answer_key_authority": "governed_signed_registry",
            "_governed_certified_grading_authority": True,
            "compiled_context": {
                "diagnostic_policy": {"official_score_allowed": True},
                "provenance": {"registry_status": "published"},
            },
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {
                "concept": "1A432000",
                "certified_grading_policy": {
                    "status": "published",
                    "policy_id": "policy-case-v1",
                    "rubric_hash": "sha256:rubric",
                    "grader_version": "rubric-grader-v1",
                    "confidence": 0.93,
                    "conflict_status": "resolved",
                },
            },
        },
        turn_id="turn-1",
    )

    assert "trusted_adjudication" not in payload["quality"]
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"


def test_uncertified_grading_policy_stays_l0_observed() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {
                "concept": "1A432000",
                "certified_grading_policy": {
                    "status": "draft",
                    "policy_id": "policy-case-v1",
                    "rubric_hash": "sha256:rubric",
                    "grader_version": "rubric-grader-v1",
                    "confidence": 0.93,
                },
            },
        },
        turn_id="turn-1",
    )

    assert "trusted_adjudication" not in payload["quality"]
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
    assert "claim_promotion_allowed" not in payload


def test_missing_question_id_caps_evidence_at_l0() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
        },
        turn_id="turn-1",
    )

    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert "missing_question_id" in payload["quality"]["evidence_cap_reasons"]


def test_rag_degraded_caps_evidence_at_l0() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 0,
            "max_score": 1,
            "evidence_refs": [
                {
                    "source": "kb_chunks",
                    "field": "chunk-1",
                    "retrieval_status": "degraded",
                }
            ],
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
        },
        turn_id="turn-1",
    )

    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert "rag_degraded" in payload["quality"]["evidence_cap_reasons"]


def test_missing_rag_evidence_caps_evidence_at_l0() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
        },
        turn_id="turn-1",
    )

    assert payload["rag_evidence_refs"] == []
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert "missing_rag_evidence" in payload["quality"]["evidence_cap_reasons"]


def test_learning_evidence_keeps_trace_reference() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "trace_id": "trace-123",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
        },
        turn_id="turn-1",
    )

    assert {"source_type": "trace", "source_id": "trace-123"} in payload["evidence_refs"]


def test_learning_evidence_attaches_canonical_topic_before_code_fallback() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-temporary-electricity",
            "question_stem": "指出施工现场临时用电管理中的不妥之处。",
            "score_awarded": 0,
            "max_score": 5,
            "node_code": "1A432000",
            "error_events": [
                {
                    "error_code": "E02",
                    "concept_tag": "1A432000",
                    "diagnosis": "漏写临时用电组织设计。",
                }
            ],
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "施工现场临时用电",
            },
        },
        turn_id="turn-1",
    )

    assert payload["canonical_topic"]["label"] == "施工临时用电"
    assert payload["canonical_topic"]["taxonomy_code"] == "1A431050"
def test_learning_evidence_carries_m35_artifact_version_and_point_matches() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "Q1-NA",
            "score_awarded": 6,
            "max_score": 10,
            "rubric": {
                "artifact_version": "m35_case_scoring_20260609",
                "rubric_mode": "curated_rubric",
                "scoring_points": [
                    {"point_id": "Q1-NA::P1", "label": "专家论证", "max_score": 2},
                    {"point_id": "Q1-NA::P2", "label": "专项方案审批", "max_score": 2},
                    {"point_id": "Q1-NA::P3", "label": "安全技术交底", "max_score": 2},
                ],
                "scoring_point_hits": [
                    {
                        "point_id": "Q1-NA::P1",
                        "hit": True,
                        "awarded_score": 2,
                        "evidence_span": "专家论证",
                        "source_ref_ids": ["2026_case_set_x#p1"],
                    },
                    {
                        "point_id": "Q1-NA::P2",
                        "hit": "partial",
                        "awarded_score": 1,
                        "evidence_span": "编制专项方案",
                        "error_code": "E02",
                        "mistake_type": "list_incomplete",
                        "source_refs": [{"ref_id": "2026_case_set_x#p2", "kind": "exam_reference_answer"}],
                    },
                    {
                        "point_id": "Q1-NA::P3",
                        "hit": False,
                        "awarded_score": 0,
                        "error_code": "E02",
                        "mistake_type": "omitted",
                        "evidence_span": "",
                        "source_ref_ids": ["2026_case_set_x#p3"],
                        "high_risk_review": True,
                    },
                ],
            },
        },
    )

    assert payload["rubric"]["artifact_version"] == "m35_case_scoring_20260609"
    assert payload["canonical_truth_written"] is False
    hits = payload["rubric"]["scoring_point_hits"]
    assert hits[0]["point_id"] == "Q1-NA::P1"
    assert hits[0]["match_status"] == "hit"
    assert hits[0]["source_ref_ids"] == ["2026_case_set_x#p1"]
    assert hits[1]["match_status"] == "partial"
    assert hits[1]["awarded_score"] == 1
    assert hits[1]["evidence_span"] == "编制专项方案"
    assert hits[1]["miss_reason"] == "list_incomplete"
    assert hits[1]["mistake_type"] == "list_incomplete"
    assert hits[1]["source_ref_ids"] == ["2026_case_set_x#p2"]
    assert hits[2]["match_status"] == "miss"
    assert hits[2]["evidence_span"] == ""
    assert hits[2]["high_risk_review"] is True


def test_non_m35_certified_artifact_version_is_not_force_clamped_to_preview() -> None:
    payload = build_learning_evidence_payload(
        grading_result={
            "type": "case",
            "question_id": "case-1",
            "score_awarded": 1,
            "max_score": 1,
            "rubric": {
                "artifact_version": "certified_policy_case_v1",
                "rubric_mode": "curated_rubric",
            },
            "error_events": [{"error_code": "E02", "concept_tag": "1A432000"}],
            "next_training_signal": {
                "concept": "1A432000",
                "certified_grading_policy": {
                    "status": "published",
                    "policy_id": "policy-case-v1",
                    "rubric_hash": "sha256:rubric",
                    "grader_version": "rubric-grader-v1",
                    "confidence": 0.93,
                    "conflict_status": "resolved",
                },
            },
        },
    )

    assert payload["rubric"]["artifact_version"] == "certified_policy_case_v1"
    # Not an M35 artifact: the M35 preview clamp must NOT force these keys on.
    assert "preview_only" not in payload
    assert "claim_promotion_allowed" not in payload
    # Client-supplied certified policy without a governed release authority stamp
    # stays formative evidence (main's trusted-adjudication hardening).
    assert payload["quality"]["evidence_level"] == "L0_observed"
