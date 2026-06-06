from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.best_quality_ai_draft import CACHED_4MODEL
from scripts.run_real_answer_teacher_review_pilot import (
    PILOT_SAMPLE_SPECS,
    PilotFakeLearnerStateService,
    build_missing_artifact_case_record,
    run_real_answer_teacher_review_pilot,
)

# DEV/EVAL-ONLY: this pilot drives the best_quality_4model engine, which needs the cached
# 4-model benchmark predictions (review/eval data, gitignored, NOT a limited-default runtime
# dependency). Skip in a clean checkout where that eval cache is absent. The limited-default
# runtime path (deepseek_fast / llm_adjudication + the tracked runtime supply bundle) is covered
# by the gate / registry / adjudicator / ws tests, which run without artifacts.
pytestmark = pytest.mark.skipif(
    not CACHED_4MODEL.exists(),
    reason="cached 4-model eval predictions absent (dev/eval-only; not a limited-default runtime dependency)",
)


def test_real_answer_pilot_generates_best_quality_drafts() -> None:
    out = run_real_answer_teacher_review_pilot()

    assert len(out["pilot_cases"]) == 5
    assert len(out["ai_draft_outputs"]) == 5
    assert {case["answer_type"] for case in out["pilot_cases"]} == {"existing_fixture"}
    assert all(draft["engine"] == "best_quality_4model" for draft in out["ai_draft_outputs"])
    assert all(case["artifact_status"] in {"published", "draft"} for case in out["pilot_cases"])


def test_artifact_missing_sample_is_not_auto_certified() -> None:
    record = build_missing_artifact_case_record(case_id="NO-SUCH-CASE", student_id="S1")

    assert record["artifact_status"] == "artifact_missing"
    assert record["auto_certified_score"] == 0
    assert record["writeback_candidate"] is False


def test_teacher_reviewed_gate_controls_writeback() -> None:
    blocked = run_real_answer_teacher_review_pilot(teacher_reviewed=False)

    assert blocked["writeback_outputs"]
    assert all(item["written_event_count"] == 0 for item in blocked["writeback_outputs"])
    assert all(item["blocked_reason"] == "teacher_reviewed_required" for item in blocked["writeback_outputs"])


def test_fake_writeback_can_read_back_learning_events() -> None:
    service = PilotFakeLearnerStateService()
    out = run_real_answer_teacher_review_pilot(learner_state_service=service)

    total_written = sum(item["written_event_count"] for item in out["writeback_outputs"])
    assert total_written >= 5
    assert len(out["readback_learning_events"]) == total_written
    assert all(event["memory_kind"] == "learning_evidence" for event in out["readback_learning_events"])


def test_high_risk_unconfirmed_points_do_not_become_mastery() -> None:
    out = run_real_answer_teacher_review_pilot()

    high_risk_points = [
        point
        for payload in out["teacher_review_payloads"]
        for point in payload["point_reviews"]
        if point.get("high_risk_review") and point.get("review_action") != "override"
    ]
    assert high_risk_points
    assert all(point["teacher_hit"] != "hit" for point in high_risk_points)
    assert all(point["teacher_score"] == 0 for point in high_risk_points)


def test_teacher_final_score_overrides_ai_draft() -> None:
    out = run_real_answer_teacher_review_pilot()

    override_points = [
        point
        for payload in out["teacher_review_payloads"]
        for point in payload["point_reviews"]
        if point.get("review_action") == "override"
    ]
    assert override_points
    assert any(point["teacher_score"] != point["ai_score"] for point in override_points)
    writeback_points = [
        point
        for item in out["writeback_outputs"]
        for event in item["captured_memory_events"]
        for point in event["payload_json"]["next_training_signal"]["teacher_review_points"]
    ]
    assert any(point["authority"] == "teacher_override" for point in writeback_points)


def test_synthesis_preview_contains_weakness_and_mastery() -> None:
    out = run_real_answer_teacher_review_pilot()
    synthesis = out["learning_brain_synthesis"]

    assert synthesis["weaknesses"], synthesis
    assert synthesis["mastery_signals"], synthesis
    assert synthesis["next_suggestions"], synthesis
    assert synthesis["read_model"]["ok"] is True


def test_pilot_does_not_call_kernel_or_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel

    monkeypatch.setattr(
        CaseGradingSkillKernel,
        "grade",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("kernel must not be called")),
    )

    out = run_real_answer_teacher_review_pilot()

    assert out["safety"]["kernel_called"] is False
    assert out["safety"]["rag_called"] is False
    assert out["safety"]["new_tables"] == []


def test_pilot_sample_specs_cover_required_policy_shapes() -> None:
    assert len(PILOT_SAMPLE_SPECS) == 5
    assert {spec["coverage"] for spec in PILOT_SAMPLE_SPECS} >= {
        "exact_required_near_term",
        "list_rule_incomplete",
        "calculation_error",
        "mostly_correct",
        "penalty_or_direction_error",
    }
