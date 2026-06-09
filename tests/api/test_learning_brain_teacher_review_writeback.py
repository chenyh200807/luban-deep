from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.routers import learning_brain as lb


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(lb.router, prefix="/api/v1/learning-brain")
    return app


def _review(teacher_reviewed=True):
    return {
        "engine": "best_quality_4model", "authority": "best_quality_4model_shadow",
        "case_id": "Q10-1A422000", "student_id": "S2", "teacher_reviewed": teacher_reviewed,
        "point_reviews": [
            # AI partial + high_risk -> teacher overrides to miss/0 (踩字)
            {"point_id": "P4", "label": "官方术语", "policy_type": "exact_required", "max_score": 2,
             "ai_hit": "partial", "ai_score": 0.5, "high_risk_review": True, "unsupported": False,
             "review_action": "override", "teacher_hit": "miss", "teacher_score": 0, "teacher_note": "近义不给分"},
            # AI hit, auto_certified -> teacher confirms
            {"point_id": "P1", "label": "术语A", "policy_type": "exact_required", "max_score": 2,
             "ai_hit": "hit", "ai_score": 2, "auto_certified": True, "review_action": "confirm"},
            # AI hit but high_risk, NOT reviewed -> downweighted, never mastery (guard parity)
            {"point_id": "P5", "label": "列举", "policy_type": "list_rule", "max_score": 2,
             "ai_hit": "hit", "ai_score": 2, "high_risk_review": True, "review_action": ""},
        ],
    }


@pytest.fixture(autouse=True)
def _qa_on(monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


def test_qa_disabled_rejects(monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "0")
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": _review()})
    assert r.status_code == 404


def test_dry_run_default_does_not_write(monkeypatch):
    # any DB write would call get_learner_state_service -> blow up
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: (_ for _ in ()).throw(AssertionError("must not write in dry_run")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": _review()})
    assert r.status_code == 200
    b = r.json()
    assert b["dry_run"] is True and b["writeback_performed"] is False
    assert b["learner_memory_event_count"] == 0
    assert isinstance(b["skipped_points"], list)
    assert b["authority"] == "teacher_reviewed_grading"
    assert isinstance(b["learning_evidence_payload_preview"], dict)


def test_teacher_override_is_higher_authority(monkeypatch):
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": _review()}).json()
    summ = b["point_event_summary"]
    assert summ["overridden"] >= 1
    # P4 overridden to miss -> not mastery; P5 high_risk unreviewed -> downweighted, not mastery
    assert "P4" not in b["mastery_point_ids"]
    assert "P5" not in b["mastery_point_ids"]
    assert summ["downweighted_high_risk_or_unsupported"] >= 1


def test_high_risk_without_review_is_downweighted_not_mastery(monkeypatch):
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": _review()}).json()
    plan = {r["point_id"]: r for r in b["write_plan"]}
    assert plan["P5"]["mastery_eligible"] is False
    assert b["memory_write_policy"]["high_risk_without_teacher_review"].startswith("downweighted")


def test_writeback_blocked_without_trusted_adjudication(monkeypatch):
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: object())
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review",
                        json={"review": _review(teacher_reviewed=False), "dry_run": False, "writeback": True})
    assert r.status_code == 400  # trusted adjudication is required to write


def test_payload_without_trusted_adjudication_is_rejected_even_for_dry_run(monkeypatch):
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: (_ for _ in ()).throw(AssertionError("must not write")))
    with TestClient(_build_app()) as client:
        r = client.post(
            "/api/v1/learning-brain/harness-case-grading-review",
            json={"review": _review(teacher_reviewed=False)},
    )
    assert r.status_code == 400


def test_ai_jury_final_adjudication_is_accepted_without_teacher_reviewed(monkeypatch):
    review = _review(teacher_reviewed=False)
    review.update(
        {
            "review_source": "model_jury_teacher_review",
            "reviewer_type": "llm_jury",
            "authority_label": "model_jury_final",
            "jury_models": ["gpt55", "opus48", "deepseek_v4", "qwen37"],
            "adjudication_protocol": "teacher_review_jury_v1",
            "confidence": 0.93,
            "conflict_status": "resolved",
        }
    )
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": review})

    assert r.status_code == 200
    preview = r.json()["learning_evidence_payload_preview"]
    assert preview["next_training_signal"]["final_adjudication_result"]["trusted_adjudication"]["source"] == "llm_jury"
    assert preview["quality"]["trusted_adjudication"]["source"] == "llm_jury"


def test_writeback_true_uses_existing_write_authority(monkeypatch):
    captured = {}

    def _fake_grader(review, *, dry_run, learner_state_service, user_id):
        captured["dry_run"] = dry_run
        captured["has_service"] = learner_state_service is not None
        return {"dry_run": dry_run, "writeback_count": 1, "write_plan": [], "mastery_point_ids": [],
                "learning_evidence_payload": {"ok": True}, "case_id": "Q10-1A422000", "engine": "best_quality_4model"}

    monkeypatch.setattr(lb, "_teacher_review_grader", _fake_grader)
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: object())
    # must NOT call the kernel
    monkeypatch.setattr(lb.CaseGradingSkillKernel, "grade", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no kernel")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review",
                        json={"review": _review(), "dry_run": False, "writeback": True, "user_id": "qa_teacher_review_20260604"})
    assert r.status_code == 200
    assert captured["dry_run"] is False and captured["has_service"] is True
    assert r.json()["writeback_performed"] is True
    assert r.json()["learner_memory_event_count"] == 1


def test_writeback_true_rejects_non_qa_user_id(monkeypatch):
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: (_ for _ in ()).throw(AssertionError("must not write unsafe user")))
    with TestClient(_build_app()) as client:
        r = client.post(
            "/api/v1/learning-brain/harness-case-grading-review",
            json={"review": _review(), "dry_run": False, "writeback": True, "user_id": "real_student_123"},
        )
    assert r.status_code == 400


def test_writeback_true_but_dry_run_true_does_not_get_service(monkeypatch):
    captured = {}

    def _fake_grader(review, *, dry_run, learner_state_service, user_id):
        captured["dry_run"] = dry_run
        captured["has_service"] = learner_state_service is not None
        return {"dry_run": dry_run, "writeback_count": 0, "write_plan": [], "mastery_point_ids": [],
                "learning_evidence_payload": {"ok": True}, "case_id": "Q10-1A422000", "engine": "best_quality_4model"}

    monkeypatch.setattr(lb, "_teacher_review_grader", _fake_grader)
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: (_ for _ in ()).throw(AssertionError("must not write in dry_run")))
    with TestClient(_build_app()) as client:
        r = client.post(
            "/api/v1/learning-brain/harness-case-grading-review",
            json={"review": _review(), "dry_run": True, "writeback": True},
        )
    assert r.status_code == 200
    assert captured == {"dry_run": True, "has_service": False}
    assert r.json()["writeback_performed"] is False


def test_invalid_score_returns_400(monkeypatch):
    bad = _review()
    bad["point_reviews"][0]["teacher_score"] = 99  # override > max_score 2 -> router rejects
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": bad})
    assert r.status_code == 400


def test_invalid_hit_returns_400(monkeypatch):
    bad = _review()
    bad["point_reviews"][0]["teacher_hit"] = "excellent"  # invalid label on an override
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": bad})
    assert r.status_code == 400


def test_manual_review_audit_metadata_is_preserved_in_preview(monkeypatch):
    review = _review()
    review.update(
        {
            "review_source": "manual_qa_teacher",
            "authority_label": "teacher_final",
            "reviewer_id": "qa_reviewer_01",
            "reviewed_at": "2026-06-04T12:00:00+08:00",
            "review_duration_seconds": 184,
            "review_ui_version": "teacher_review_ux_v0",
        }
    )

    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading-review", json={"review": review})

    assert r.status_code == 200
    preview = r.json()["learning_evidence_payload_preview"]
    signal = preview["next_training_signal"]
    assert signal["teacher_review_audit"] == {
        "review_source": "manual_qa_teacher",
        "authority_label": "teacher_final",
        "reviewer_id": "qa_reviewer_01",
        "reviewed_at": "2026-06-04T12:00:00+08:00",
        "review_duration_seconds": 184,
        "review_ui_version": "teacher_review_ux_v0",
    }
    assert signal["teacher_final_grading_result"]["teacher_review_audit"]["reviewer_id"] == "qa_reviewer_01"
