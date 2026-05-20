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
