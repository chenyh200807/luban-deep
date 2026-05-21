from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.routers import learning_brain as learning_brain_router
from deeptutor.services.learner_state.service import LearnerStateService
from deeptutor.services.path_service import PathService


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(learning_brain_router.router, prefix="/api/v1/learning-brain")
    return app


def test_learning_brain_harness_case_grading_runs_visible_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path / "user-data"))
    PathService.reset_instance()
    service = LearnerStateService()
    monkeypatch.setattr(learning_brain_router, "get_learner_state_service", lambda: service)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={
                "user_id": "qa_student",
                "user_answer": "应加强现场管理，落实责任，严格检查。",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["projection_subject"] == "construction_exam_learning_truth"
    assert payload["event_count"] == 2
    assert payload["created_claim_count"] >= 1
    assert payload["typed_graph_edge_count"] > 0
    assert payload["typed_graph_edges"]
    assert payload["compiled_objects"]
    assert payload["visible_sections"]
    assert any(edge["edge_type"] == "question_tests_concept" for edge in payload["typed_graph_edges"])
    assert payload["training_uses_question"] is True
    assert payload["graph_chain"]["training_uses_question"]
    assert payload["training_improved_error"] or payload["training_not_improved_error"]
    assert payload["graph_chain"]["training_improved_error"] or payload["graph_chain"]["training_not_improved_error"]
    assert payload["grading_results"][0]["score_label"] == "0/1"
    assert payload["grading_results"][0]["missed_points"]
    assert payload["grading_results"][0]["rewrite"]
    assert payload["grading_results"][0]["next_training_signal"]["concept"] == "1A432000"
    assert any(item["evidence_level"] == "L1_repeated" for item in payload["weak_points"])


def test_learning_brain_harness_html_escapes_dynamic_projection_text() -> None:
    html = learning_brain_router.render_learning_brain_harness_html()

    assert "function escapeHtml" in html
    assert ".replace(/&/g" in html
    assert ".replace(/</g" in html
    assert "return escapeHtml(String(value || \"\")" in html


def test_learning_brain_harness_manual_confirmation_upgrades_l2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path / "user-data"))
    PathService.reset_instance()
    service = LearnerStateService()
    monkeypatch.setattr(learning_brain_router, "get_learner_state_service", lambda: service)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={
                "user_id": "qa_student",
                "user_answer": "只写加强现场管理，没有写专家论证、专项施工方案审批和验收程序。",
                "manual_confirm": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["manual_confirmation"]["event_id"]
    assert payload["event_count"] == 3
    assert any(item["evidence_level"] == "L2_confirmed" for item in payload["weak_points"])
    concept = payload["compiled_objects"]["concept:1A432000"]
    assert concept["evidence_level"] == "L2_confirmed"
    assert payload["manual_confirmation"]["event_id"] in concept["supporting_event_ids"]


def test_learning_brain_harness_success_training_persists_improvement_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path / "user-data"))
    PathService.reset_instance()
    service = LearnerStateService()
    monkeypatch.setattr(learning_brain_router, "get_learner_state_service", lambda: service)

    with TestClient(_build_app()) as client:
        first = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={
                "user_id": "qa_student",
                "user_answer": "只写加强现场管理，没有写专家论证、专项施工方案审批和验收程序。",
            },
        )
        second = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={
                "user_id": "qa_student",
                "user_answer": "应组织专家论证，编制专项施工方案并按规定审批；按专项施工方案实施，验收合格后方可进入下道工序。",
            },
        )

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["graph_chain"]["has_training_not_improved_error"] is True

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["event_count"] == 4
    assert second_payload["graph_chain"]["has_training_uses_question"] is True
    assert second_payload["graph_chain"]["has_training_improved_error"] is True
    assert second_payload["improvement_signals"]
    # Note: ``stale_claims`` stays empty here by design. The harness flow only
    # produces concept-only improvement signals (no typed error edge on
    # success), and ``test_concept_only_improvement_signal_does_not_clear_specific_weak_points``
    # locks in that concept-only improvements never decay specific (concept,
    # error_code) weak points at the synthesis layer. Improvement visibility
    # for the graph chain is asserted above via ``has_training_improved_error``.
    assert second_payload["stale_claims"] == []


def test_learning_brain_projection_returns_wechat_read_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path / "user-data"))
    PathService.reset_instance()
    service = LearnerStateService()
    monkeypatch.setattr(learning_brain_router, "get_learner_state_service", lambda: service)

    with TestClient(_build_app()) as client:
        harness_response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={
                "user_id": "qa_student",
                "user_answer": "应加强现场管理，落实责任，严格检查。",
            },
        )
        response = client.get("/api/v1/learning-brain/harness-projection", params={"user_id": "qa_student"})

    assert harness_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["user_id"] == "qa_student"
    assert payload["projection_subject"] == "construction_exam_learning_truth"
    assert payload["compiled_objects"]
    assert payload["weak_points"]
    assert set(payload["visible_sections"]) == {"current_truth", "evidence_flow", "next_training"}
    assert payload["visible_sections"]["current_truth"]
    assert payload["visible_sections"]["evidence_flow"]
    assert payload["visible_sections"]["next_training"]
    assert payload["visible_sections"]["current_truth"][0]["display_title"].startswith("工程招标投标与合同管理")
    assert payload["typed_graph_edge_count"] > 0


def test_learning_brain_harness_is_disabled_without_explicit_local_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.delenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", raising=False)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={"user_id": "qa_student", "user_answer": "应加强现场管理。"},
        )

    assert response.status_code == 404


def test_learning_brain_projection_is_disabled_without_explicit_local_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.delenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", raising=False)

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/learning-brain/harness-projection", params={"user_id": "qa_student"})

    assert response.status_code == 404


def test_learning_brain_harness_is_disabled_in_staging_even_with_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "staging")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={"user_id": "qa_student", "user_answer": "应加强现场管理。"},
        )

    assert response.status_code == 404


def test_learning_brain_harness_is_disabled_in_production_even_with_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/learning-brain/harness-case-grading",
            json={"user_id": "qa_student", "user_answer": "应加强现场管理。"},
        )

    assert response.status_code == 404
