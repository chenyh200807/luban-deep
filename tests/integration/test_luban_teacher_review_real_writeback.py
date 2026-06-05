"""Real-backend teacher-review writeback (NOT a fake service).

This is the v2 closure the fake integration could not prove: a REAL
``LearnerStateService`` writing teacher-final point facts to its real file-backed
store (``MEMORY_EVENTS.jsonl`` under a temp ``DEEPTUTOR_USER_DATA_DIR``), then reading
them back from disk and synthesizing the Learning Brain projection.

It is QA-gated (``qa_``/``test_`` only), writes NO production user, adds NO table,
does NOT touch CaseGradingSkillKernel / RAG / production runtime, and never lets an
un-reviewed AI-Draft become mastery.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)
from deeptutor.services.learner_state.learning_brain_read_model import (
    build_learning_brain_read_model,
)

QA_STUDENT = "qa_luban_teacher_review_v2"
NON_QA_STUDENT = "real_student_v2_999"


@pytest.fixture
def real_service(tmp_path, monkeypatch):
    """A REAL LearnerStateService rooted at a temp dir (file-backed, not fake).

    The ONLY thing stubbed is the downstream home-personalization projection write
    (``_write_home_projection``), a non-authoritative cache that otherwise makes a
    ~6s network call. The learner_memory_events write authority (append_memory_event
    -> MEMORY_EVENTS.jsonl) stays 100% real and unmocked.
    """
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path))
    from deeptutor.services.construction_grading import writeback as wb

    monkeypatch.setattr(wb, "_write_home_projection", lambda **_kwargs: None)
    from deeptutor.services import path_service as ps

    ps.PathService.reset_instance()
    from deeptutor.services.learner_state.service import LearnerStateService

    service = LearnerStateService()
    yield service, tmp_path
    ps.PathService.reset_instance()


def _reviews(student_id: str) -> list[dict[str, Any]]:
    return [
        {  # 1. exact_required: teacher OVERRIDE miss, 近义不给分
            "sample_id": "exact_required_override_miss", "case_id": "Q-exact-001",
            "student_id": student_id, "engine": "best_quality_4model",
            "teacher_reviewed": True, "review_source": "qa_fixture_teacher_review",
            "point_reviews": [{
                "point_id": "P-exact-01", "label": "官方术语：专项施工方案",
                "policy_type": "exact_required", "max_score": 2,
                "ai_hit": "partial", "ai_score": 0.5, "high_risk_review": True,
                "review_action": "override", "teacher_hit": "miss", "teacher_score": 0,
                "teacher_note": "未写官方术语，近义不给分",
            }],
        },
        {  # 2. list_rule: teacher CONFIRM partial, 列举不全
            "sample_id": "list_rule_confirm_partial", "case_id": "Q-list-002",
            "student_id": student_id, "engine": "best_quality_4model",
            "teacher_reviewed": True, "review_source": "qa_fixture_teacher_review",
            "point_reviews": [{
                "point_id": "P-list-01", "label": "资源供应平衡要点",
                "policy_type": "list_rule", "max_score": 3,
                "ai_hit": "partial", "ai_score": 1.5,
                "review_action": "confirm", "teacher_hit": "partial", "teacher_score": 1.5,
                "teacher_note": "列举不全，仍缺关键要点",
            }],
        },
        {  # 3. calculation: teacher CONFIRM hit -> success / mastery evidence
            "sample_id": "calculation_confirm_hit", "case_id": "Q-calc-003",
            "student_id": student_id, "engine": "best_quality_4model",
            "teacher_reviewed": True, "review_source": "qa_fixture_teacher_review",
            "point_reviews": [{
                "point_id": "P-calc-01", "label": "流水节拍计算",
                "policy_type": "calculation", "max_score": 4,
                "ai_hit": "hit", "ai_score": 4, "auto_certified": True,
                "review_action": "confirm", "teacher_hit": "hit", "teacher_score": 4,
                "teacher_note": "公式与数值正确，结果成立",
            }],
        },
        {  # 4. high_risk_review NOT individually reviewed -> never mastery
            "sample_id": "high_risk_unreviewed", "case_id": "Q-hr-004",
            "student_id": student_id, "engine": "best_quality_4model",
            "teacher_reviewed": True, "review_source": "qa_fixture_teacher_review",
            "point_reviews": [{
                "point_id": "P-hr-01", "label": "施工组织设计审批",
                "policy_type": "exact_required", "max_score": 2,
                "ai_hit": "hit", "ai_score": 2, "high_risk_review": True,
                "review_action": "",  # left unreviewed
            }],
        },
        {  # 5. unsupported NOT reviewed -> never mastery
            "sample_id": "unsupported_unreviewed", "case_id": "Q-unsup-005",
            "student_id": student_id, "engine": "best_quality_4model",
            "teacher_reviewed": True, "review_source": "qa_fixture_teacher_review",
            "point_reviews": [{
                "point_id": "P-unsup-01", "label": "质量验收批次",
                "policy_type": "list_rule", "max_score": 2,
                "ai_hit": "hit", "ai_score": 2, "unsupported": True,
                "review_action": "",  # left unreviewed
            }],
        },
    ]


def _writeback_all(service, student_id: str) -> list[dict[str, Any]]:
    return [
        build_teacher_review_writeback(
            review, dry_run=False, learner_state_service=service, user_id=student_id
        )
        for review in _reviews(student_id)
    ]


def test_real_service_persists_teacher_review_to_disk(real_service):
    service, tmp_path = real_service
    outputs = _writeback_all(service, QA_STUDENT)

    # every review wrote exactly one real memory event
    assert [o["writeback_count"] for o in outputs] == [1, 1, 1, 1, 1]

    # PROOF of real DB: the events are on disk in MEMORY_EVENTS.jsonl
    events_file = tmp_path / "learner_state" / QA_STUDENT / "MEMORY_EVENTS.jsonl"
    assert events_file.exists()
    lines = [json.loads(line) for line in events_file.read_text("utf-8").splitlines() if line.strip()]
    assert len(lines) == 5
    assert {row["memory_kind"] for row in lines} == {"learning_evidence"}
    for row in lines:
        assert row["payload_json"]["next_training_signal"]["teacher_final_grading_result"]


def test_real_readback_and_gap_vs_mastery(real_service):
    service, _ = real_service
    _writeback_all(service, QA_STUDENT)

    events = service.list_memory_events(QA_STUDENT, limit=50)
    assert len(events) == 5
    payloads = {e.payload_json["question_id"]: e.payload_json for e in events}

    # exact_required override miss -> weakness/gap (E03)
    assert payloads["Q-exact-001"]["error_events"][0]["error_code"] == "E03"
    assert payloads["Q-exact-001"]["error_events"][0]["diagnosis"] == "未写官方术语，近义不给分"
    # list_rule partial -> weakness/gap (E02)
    assert payloads["Q-list-002"]["error_events"][0]["error_code"] == "E02"
    # calculation full hit -> success, NO error event
    assert payloads["Q-calc-003"]["error_events"] == []
    # high_risk / unsupported unreviewed -> still a gap, never mastery
    assert payloads["Q-hr-004"]["error_events"]
    assert payloads["Q-unsup-005"]["error_events"]


def test_mastery_gating_and_override_authority(real_service):
    service, _ = real_service
    outputs = {o["case_id"]: o for o in _writeback_all(service, QA_STUDENT)}

    # only the teacher-confirmed full-hit calculation point is mastery
    assert outputs["Q-calc-003"]["mastery_point_ids"] == ["P-calc-01"]
    # override miss is NOT mastery (teacher override > AI partial)
    exact_row = outputs["Q-exact-001"]["write_plan"][0]
    assert exact_row["authority"] == "teacher_override"
    assert exact_row["final_hit"] == "miss"
    assert exact_row["mastery_eligible"] is False
    # high_risk / unsupported unreviewed -> never mastery
    assert outputs["Q-hr-004"]["write_plan"][0]["mastery_eligible"] is False
    assert outputs["Q-unsup-005"]["write_plan"][0]["mastery_eligible"] is False


def test_learning_brain_reads_back_weakness_and_mastery(real_service):
    service, _ = real_service
    _writeback_all(service, QA_STUDENT)

    synthesis = service.synthesize_learning_truth(QA_STUDENT, dry_run=True, event_limit=50)
    projection = synthesis["projection"]
    read_model = build_learning_brain_read_model(
        user_id=QA_STUDENT, projection=projection, surface="qa"
    )
    assert read_model["event_count"] == 5
    # Mastery (calculation full hit) surfaces as an improvement signal.
    assert any(item["concept_id"] == "流水节拍计算" for item in read_model["improvement_signals"])
    # A single teacher-reviewed gap is surfaced as an observed weakness candidate
    # (the real read model promotes to confirmed weak_points only with more evidence).
    weakness_concepts = {
        item.get("concept_id")
        for item in (read_model.get("weak_points") or []) + (projection.get("observed_candidates") or [])
    }
    assert "官方术语：专项施工方案" in weakness_concepts
    # the weakness candidate carries a next-step training recommendation (next suggestion).
    exact_candidate = next(
        c for c in projection["observed_candidates"]
        if c.get("concept_id") == "官方术语：专项施工方案"
    )
    assert exact_candidate.get("recommended_training")


def test_non_qa_user_is_fail_closed_no_write(real_service):
    service, tmp_path = real_service
    outputs = _writeback_all(service, NON_QA_STUDENT)
    assert all(o["writeback_count"] == 0 for o in outputs)
    assert all(o["writeback_skipped_reason"] == "qa_user_id_required" for o in outputs)
    # nothing on disk for the non-QA user
    assert not (tmp_path / "learner_state" / NON_QA_STUDENT / "MEMORY_EVENTS.jsonl").exists()


def test_ai_draft_without_teacher_review_is_not_written(real_service):
    service, tmp_path = real_service
    review = _reviews(QA_STUDENT)[0]
    review = {**review, "teacher_reviewed": False}  # un-reviewed AI draft
    out = build_teacher_review_writeback(
        review, dry_run=False, learner_state_service=service, user_id=QA_STUDENT
    )
    assert out["writeback_count"] == 0
    assert out["writeback_skipped_reason"] == "teacher_reviewed_required"
    assert not (tmp_path / "learner_state" / QA_STUDENT / "MEMORY_EVENTS.jsonl").exists()
