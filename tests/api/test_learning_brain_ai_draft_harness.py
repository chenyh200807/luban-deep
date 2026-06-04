from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.routers import learning_brain as lb
from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(lb.router, prefix="/api/v1/learning-brain")
    return app


# a deterministic AI-Draft (no live model): one exact_required clean hit + one
# list_rule partial that the abstention proxy routes to pending_review.
_FIXTURE_QUESTION = {
    "case_id": "QX", "max_score": 4,
    "scoring_points": [
        {"point_id": "P1", "max_score": 2, "label": "官方术语 A", "typed_policy": {"policy_type": "exact_required", "required_terms": ["专项施工方案"]}},
        {"point_id": "P2", "max_score": 2, "label": "列举项", "typed_policy": {"policy_type": "list_rule", "required_terms": ["甲", "乙"], "denominator": 2}},
    ],
}
_FIXTURE_ANSWER = "采用了专项施工方案；还写了甲"
_FIXTURE_PREDS = [
    {"point_id": "P1", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "逐字命中官方术语"},
    {"point_id": "P2", "hit": "partial", "score": 1, "evidence_span": "甲", "rationale": "只覆盖一半,缺少乙"},
]


def _fixture_grader(case_row, answer):  # noqa: ARG001
    return build_ai_draft(_FIXTURE_QUESTION, _FIXTURE_ANSWER, _FIXTURE_PREDS, points=_FIXTURE_QUESTION["scoring_points"], student_id="harness")


@pytest.fixture(autouse=True)
def _qa_on(monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


def test_harness_html_contains_ai_draft_panel():
    html = lb.render_learning_brain_harness_html()
    # panel inputs + run/export controls
    for token in ("aiCaseId", "aiAnswer", "runAiDraft", "exportReview", "AI-Draft 阅卷"):
        assert token in html
    # three-score semantics surfaced (pending not shown as 0)
    for token in ("model_draft_score", "auto_certified_score", "pending_review_score", "bad_certified_count"):
        assert token in html
    # distinct visual status classes: auto(green)/pending(amber)/unsupported(red)
    for token in ("st-auto", "st-pending", "st-unsupported", "b-pending", "b-unsupported"):
        assert token in html
    # evidence_span highlight + teacher-review override/export structure
    for token in ("highlightSpan", "<mark>", "tr-hit", "tr-score", "tr-note", "point_reviews", "teacher_hit", "review_action"):
        assert token in html
    # calls the existing endpoint with ai_draft mode + writeback:false (no second endpoint)
    assert "/api/v1/learning-brain/harness-case-grading" in html
    assert "writeback:false" in html


def test_html_has_engine_toggle_and_votes_display():
    html = lb.render_learning_brain_harness_html()
    for token in ("aiEngine", "best_quality_4model", "deepseek_fast", "aiStudent", "model_votes", "adjudication_reason", "四模型"):
        assert token in html
    assert "engine:engine" in html  # request sends engine


def test_engine_best_quality_calls_new_service(monkeypatch):
    captured = {}

    def _bq(case_row, student_id):
        captured["called"] = True
        return build_ai_draft(_FIXTURE_QUESTION, _FIXTURE_ANSWER, _FIXTURE_PREDS, points=_FIXTURE_QUESTION["scoring_points"], student_id=student_id) | {
            "authority": "best_quality_4model_shadow", "engine": "best_quality_4model",
            "prediction_source": "cached_4model_485", "model_set": ["gpt55", "opus48", "deepseek_v4", "qwen37"]}

    monkeypatch.setattr(lb, "_best_quality_grader", _bq)
    # best-quality must NOT call deepseek_fast grader nor kernel
    monkeypatch.setattr(lb, "_ai_draft_grader", lambda *a, **k: (_ for _ in ()).throw(AssertionError("best_quality must not call deepseek_fast")))
    monkeypatch.setattr(lb.CaseGradingSkillKernel, "grade", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call kernel")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading",
                        json={"user_id": "qa", "user_answer": "x", "mode": "ai_draft", "engine": "best_quality_4model", "case_id": "Q10-1A422000", "student_id": "S2"})
    assert r.status_code == 200
    b = r.json()
    assert captured.get("called") is True
    assert b["authority"] == "best_quality_4model_shadow" and b["engine"] == "best_quality_4model"
    assert b["prediction_source"] == "cached_4model_485"


def test_engine_default_is_deepseek_fast(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    monkeypatch.setattr(lb, "_best_quality_grader", lambda *a, **k: (_ for _ in ()).throw(AssertionError("default must not call best_quality")))
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft"}).json()
    assert b["engine"] == "deepseek_fast" and b["authority"] == "ai_draft_shadow"


def test_best_quality_fail_closed_when_unavailable(monkeypatch):
    from deeptutor.services.construction_grading.best_quality_ai_draft import BestQualityUnavailable
    monkeypatch.setattr(lb, "_best_quality_grader", lambda *a, **k: (_ for _ in ()).throw(BestQualityUnavailable("no cached predictions")))
    monkeypatch.setattr(lb, "_ai_draft_grader", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fall back to DeepSeek")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading",
                        json={"user_id": "qa", "user_answer": "x", "mode": "ai_draft", "engine": "best_quality_4model"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "best_quality_unavailable"


def test_qa_disabled_rejects(monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "0")
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": "x", "mode": "ai_draft"})
    assert r.status_code == 404


def test_ai_draft_returns_shadow_markers(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft"})
    assert r.status_code == 200
    b = r.json()
    assert b["authority"] == "ai_draft_shadow"
    assert b["candidate_only"] is True and b["not_production_grade"] is True
    assert b["dry_run"] is True and b["writeback_performed"] is False


def test_ai_draft_dry_run_does_not_write(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    # if the ai_draft path tried to write, it would call get_learner_state_service; make it explode
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: (_ for _ in ()).throw(AssertionError("must not write in ai_draft dry_run")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft", "writeback": True})
    assert r.status_code == 200
    assert r.json()["writeback_performed"] is False
    assert r.json()["writeback_requested_ignored_this_round"] is True


def test_ai_draft_does_not_touch_kernel(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    monkeypatch.setattr(lb.CaseGradingSkillKernel, "grade",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ai_draft must not call CaseGradingSkillKernel")))
    with TestClient(_build_app()) as client:
        r = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft"})
    assert r.status_code == 200


def test_ai_draft_high_risk_not_auto_certified_and_pending_returned(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft"}).json()
    assert "pending_review_score" in b and "auto_certified_score" in b and "model_draft_score" in b
    assert b["bad_certified_count"] == 0
    for p in b["point_results"]:
        assert "display_status" in p and "max_score" in p and "expected_point_label" in p
        if p["high_risk_review"] or p["unsupported"]:
            assert p["auto_certified"] is False
    # the list_rule partial (P2) is routed to pending_review and its score is preserved (not 0)
    assert b["pending_review_score"] >= 1.0
    assert b["model_draft_score"] >= b["auto_certified_score"]


def test_ai_draft_payload_preview_present(monkeypatch):
    monkeypatch.setattr(lb, "_ai_draft_grader", _fixture_grader)
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": _FIXTURE_ANSWER, "mode": "ai_draft"}).json()
    assert isinstance(b["learning_evidence_payload_preview"], dict) and b["learning_evidence_payload_preview"]


def test_kernel_mode_default_preserves_original_behavior(monkeypatch):
    # mode != ai_draft must NOT return the ai_draft shadow markers
    sentinel = {"called": False}

    class _DummyLearnerStateService:
        def synthesize_learning_truth(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return {"projection": {}}

    def _kernel_grade(self, **kwargs):  # noqa: ANN001
        sentinel["called"] = True
        from deeptutor.services.construction_grading.schema import CaseGradingResult
        return CaseGradingResult(question_id="q", grading_mode="open_skill", score_awarded=0.0, max_score=1.0, rubric_items=[])

    monkeypatch.setattr(lb.CaseGradingSkillKernel, "grade", _kernel_grade)
    monkeypatch.setattr(lb, "write_grading_error_events", lambda **k: 0)
    monkeypatch.setattr(lb, "get_learner_state_service", lambda: _DummyLearnerStateService())
    with TestClient(_build_app()) as client:
        b = client.post("/api/v1/learning-brain/harness-case-grading", json={"user_id": "qa", "user_answer": "应组织专家论证"}).json()
    assert b.get("authority") != "ai_draft_shadow"
    assert sentinel["called"] is True  # kernel path was taken
