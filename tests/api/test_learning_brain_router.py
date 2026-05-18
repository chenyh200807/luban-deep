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
    assert any(edge["edge_type"] == "question_tests_concept" for edge in payload["typed_graph_edges"])
    assert payload["grading_results"][0]["score_label"] == "0/1"
    assert payload["grading_results"][0]["missed_points"]
    assert payload["grading_results"][0]["rewrite"]
    assert payload["grading_results"][0]["next_training_signal"]["concept"] == "1A432000"
    assert any(item["evidence_level"] == "L1_repeated" for item in payload["weak_points"])


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
