"""LLM Jury Teacher Review pilot — real file backend, honest llm_jury labelling.

The jury votes are REAL cached 4-model predictions (485 span-guarded run), not live
calls and not fabricated. Writes to a QA/test file backend only; never claims a human.
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)
from scripts.run_luban_model_jury_teacher_review_pilot import build_jury_review

QA_USER = "qa_luban_model_jury_review_v0"
NON_QA = "real_jury_student_999"
CASE = "Q17-1A433000"
STUDENT = "S1"


@pytest.fixture
def real_service(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path))
    from deeptutor.services.construction_grading import writeback as wb

    monkeypatch.setattr(wb, "_write_home_projection", lambda **_k: None)
    from deeptutor.services import path_service as ps

    ps.PathService.reset_instance()
    from deeptutor.services.learner_state.service import LearnerStateService

    yield LearnerStateService(), tmp_path
    ps.PathService.reset_instance()


def test_review_is_llm_jury_not_manual_human():
    review, _ = build_jury_review(CASE, STUDENT)
    assert review["review_source"] == "model_jury_teacher_review"
    assert review["review_source"] != "manual_qa_teacher"
    assert review["reviewer_type"] == "llm_jury"
    assert review["authority_label"] == "trusted_adjudication"
    assert review["requires_human"] is False
    assert set(review["jury_models"]) >= {"gpt55", "opus48", "deepseek_v4", "qwen37"} - {"qwen37"}
    assert len(review["jury_models"]) >= 3  # >=3 real models or stop
    assert "manual_qa_teacher" not in json.dumps(review, ensure_ascii=False)


def test_jury_metadata_reaches_learning_brain_payload(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=QA_USER)
    assert out["writeback_count"] == 1
    events = service.list_memory_events(QA_USER, limit=10)
    audit = events[0].payload_json["next_training_signal"]["teacher_review_audit"]
    assert audit["reviewer_type"] == "llm_jury"
    assert audit["review_source"] == "model_jury_teacher_review"
    assert audit["adjudication_protocol"] == "trusted_adjudication_jury_v1"
    assert audit["authority_label"] == "trusted_adjudication"
    assert set(audit["jury_models"]) and "manual_qa_teacher" not in json.dumps(audit, ensure_ascii=False)


def test_dry_run_does_not_write(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    out = build_teacher_review_writeback(review, dry_run=True, learner_state_service=service, user_id=QA_USER)
    assert "writeback_count" not in out or out.get("writeback_count", 0) == 0
    assert not (tmp_path / "learner_state" / QA_USER / "MEMORY_EVENTS.jsonl").exists()


def test_writeback_writes_qa_file_backend(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=QA_USER)
    f = tmp_path / "learner_state" / QA_USER / "MEMORY_EVENTS.jsonl"
    assert f.exists()
    rows = [json.loads(l) for l in f.read_text("utf-8").splitlines() if l.strip()]
    assert len(rows) == 1 and rows[0]["memory_kind"] == "learning_evidence"


def test_needs_human_review_and_high_risk_not_auto_mastery(real_service):
    service, _ = real_service
    review, jury_points = build_jury_review(CASE, STUDENT)
    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=QA_USER)
    mastery = set(out["mastery_point_ids"])
    # any point the jury flagged needs_human_review must NOT be mastery
    for jp in jury_points:
        if jp["needs_human_review"]:
            assert jp["point_id"] not in mastery
    # pending (unreviewed) point_reviews never become mastery
    for pr in review["point_reviews"]:
        if pr["review_action"] == "" or pr.get("needs_human_review"):
            assert pr["point_id"] not in mastery


def test_teacher_reviewed_false_with_trusted_jury_still_writes(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    review = {**review, "teacher_reviewed": False}
    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=QA_USER)
    assert out["writeback_count"] == 1
    assert (tmp_path / "learner_state" / QA_USER / "MEMORY_EVENTS.jsonl").exists()


def test_missing_trusted_adjudication_not_written(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    review = {
        **review,
        "teacher_reviewed": False,
        "review_source": "",
        "reviewer_type": "",
        "authority_label": "",
    }
    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=QA_USER)
    assert out["writeback_count"] == 0
    assert out["writeback_skipped_reason"] == "trusted_adjudication_required"
    assert not (tmp_path / "learner_state" / QA_USER / "MEMORY_EVENTS.jsonl").exists()


def test_non_qa_user_not_written(real_service):
    service, tmp_path = real_service
    review, _ = build_jury_review(CASE, STUDENT)
    out = build_teacher_review_writeback(review, dry_run=False, learner_state_service=service, user_id=NON_QA)
    assert out["writeback_count"] == 0
    assert out["writeback_skipped_reason"] == "qa_user_id_required"
    assert not (tmp_path / "learner_state" / NON_QA / "MEMORY_EVENTS.jsonl").exists()
