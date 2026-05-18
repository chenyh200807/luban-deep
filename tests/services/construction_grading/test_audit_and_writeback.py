from __future__ import annotations

from deeptutor.services.construction_grading.audit import evaluate_grading_supabase_audit
from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.writeback import write_grading_error_events


def test_audit_accepts_projected_rubric_assets_without_requiring_curated_rubric() -> None:
    report = evaluate_grading_supabase_audit(
        {
            "questions_bank": {
                "count_total": 4638,
                "field_fill_mcq": {
                    "total": 2659,
                    "correct_answer__filled": 2659,
                    "analysis__filled": 2655,
                    "options__filled": 2655,
                    "option_reasoning__filled": 80,
                },
                "field_fill_case": {
                    "total": 1961,
                    "correct_answer__filled": 1950,
                    "analysis__filled": 1332,
                    "grading_rubric__filled": 0,
                    "grading_keywords__filled": 960,
                    "structured_rules__filled": 661,
                    "node_code__filled": 1916,
                },
            },
            "online_evidence_tables": {
                "kb_chunks": {
                    "exists": True,
                    "count_total": 15432,
                    "metadata_key_fill": {
                        "exam_matrix": 1192,
                        "structured_rules": 884,
                        "logic_chains": 1074,
                        "pitfalls": 240,
                    },
                },
                "standard_articles": {
                    "exists": True,
                    "count_total": 3319,
                    "field_fill": {"logic_constraints__filled": 908},
                },
                "syllabus_tree": {
                    "exists": True,
                    "count_total": 1284,
                    "field_fill": {"node_code__filled": 1284, "keywords__filled": 780},
                },
                "knowledge_cards": {"exists": False},
            },
        }
    )

    assert report["status"] == "pass"
    assert "projected_rubric_ready" in report["ready_modes"]
    assert "curated_rubric_ready" not in report["ready_modes"]
    assert any(issue["code"] == "curated_rubric_empty" for issue in report["issues"])


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def append_memory_event(self, user_id: str, **kwargs: object) -> object:
        self.calls.append({"user_id": user_id, **kwargs})
        return object()


def test_writeback_uses_existing_learner_memory_events() -> None:
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
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        grading_result=result,
        source_id="submission-1",
        source_bot_id="construction-exam",
    )

    assert count == 1
    call = service.calls[0]
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_bot_id"] == "construction-exam"
    assert call["dedupe_key"]
    assert call["payload_json"]["event_type"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "construction_grading_error"
    assert call["payload_json"]["question_id"] == "case-1"
    assert call["payload_json"]["error_events"][0]["error_code"] in {"E02", "E03", "E04"}
    assert call["payload_json"]["errors"][0]["error_code"] in {"E02", "E03", "E04"}
    assert call["payload_json"]["quality"]["evidence_level"] == "L0_observed"


def test_writeback_accepts_runtime_batch_dict_result() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-1",
        source_bot_id="construction-exam",
        grading_result={
            "type": "batch",
            "authority": "construction_grading",
            "items": [
                {
                    "type": "mcq",
                    "question_id": "q-1",
                    "question_type": "choice",
                    "user_answer": "A",
                    "score_awarded": 0.0,
                    "max_score": 1.0,
                    "error_events": [
                        {
                            "error_code": "M02",
                            "severity": 0.7,
                            "concept_tag": "法规层级",
                            "evidence": "A",
                            "diagnosis": "作答与标准答案不一致。",
                        }
                    ],
                    "next_training_signal": {
                        "concept": "法规层级",
                        "focus": "行政法规与部门规章辨析",
                    },
                },
                {
                    "type": "mcq",
                    "question_id": "q-2",
                    "question_type": "choice",
                    "user_answer": "B",
                    "score_awarded": 1.0,
                    "max_score": 1.0,
                    "error_events": [],
                    "next_training_signal": {},
                },
            ],
        },
    )

    assert count == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["source_id"] == "turn-1:q-1"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["question_id"] == "q-1"
    assert call["payload_json"]["next_training_signal"]["focus"] == "行政法规与部门规章辨析"


def test_writeback_can_persist_success_learning_event_for_improvement_signal() -> None:
    service = _FakeLearnerStateService()

    count = write_grading_error_events(
        learner_state_service=service,
        user_id="student-1",
        source_id="turn-2",
        source_bot_id="construction-exam",
        include_success_events=True,
        grading_result={
            "type": "case",
            "question_id": "case-2",
            "question_type": "case",
            "user_answer": "应组织专家论证，编制专项施工方案并审批。",
            "score_awarded": 1.0,
            "max_score": 1.0,
            "rubric_items": [{"rubric_item_id": "r1", "criterion": "专家论证程序", "status": "full"}],
            "error_events": [],
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "专家论证程序",
                "mode": "case_repair",
            },
        },
    )

    assert count == 1
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["error_events"] == []
    assert call["payload_json"]["score_awarded"] == 1.0
    assert call["payload_json"]["quality"]["writeback_eligible"] is True
    assert call["payload_json"]["quality"]["writeback_reason"] == "success_improvement_signal"
