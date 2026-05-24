from __future__ import annotations

import importlib
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.services.member_console.service import MemberConsoleService
from deeptutor.services.path_service import PathService


FORBIDDEN_PRE_SUBMIT_KEYS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "rubric",
    "official_answer",
    "option_reasoning",
}

FORBIDDEN_PRE_SUBMIT_KEY_SUBSTRINGS = (
    "answer",
    "grading",
    "rubric",
    "scoring_point",
    "correct",
)

_ALLOWED_PRE_SUBMIT_SUBSTRING_KEYS = {
    # Metadata only: source IDs are needed for provenance/debugging but do not
    # reveal correctness or grading artifacts.
    "source_answer_table",
}


def _assert_no_forbidden_pre_submit_keys(payload: Any, path: str = "$") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_lower = key_text.lower()
            current_path = f"{path}.{key_text}"
            assert key_lower not in FORBIDDEN_PRE_SUBMIT_KEYS, f"forbidden key leaked at {current_path}"
            if key_lower not in _ALLOWED_PRE_SUBMIT_SUBSTRING_KEYS:
                for substring in FORBIDDEN_PRE_SUBMIT_KEY_SUBSTRINGS:
                    assert substring not in key_lower, f"forbidden key substring leaked at {current_path}"
            _assert_no_forbidden_pre_submit_keys(value, current_path)
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, item in enumerate(payload):
            _assert_no_forbidden_pre_submit_keys(item, f"{path}[{index}]")


def _build_mobile_app() -> FastAPI:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    app = FastAPI()
    app.include_router(mobile_module.router, prefix="/api/v1")
    return app


def test_member_service_create_assessment_payload_is_redacted(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("redaction_user", count=20)

    _assert_no_forbidden_pre_submit_keys(payload)


def test_mobile_create_assessment_payload_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    user_data_dir = Path(tempfile.mkdtemp(prefix="deeptutor-assessment-redaction-")) / "user"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    path_service = PathService.get_instance()
    original_user_data_dir = path_service._user_data_dir
    path_service._user_data_dir = user_data_dir
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    replacement_service = MemberConsoleService()
    replacement_service._data_path = user_data_dir / "member_console.json"
    monkeypatch.setattr(mobile_module, "member_service", replacement_service)
    monkeypatch.setattr(mobile_module, "_resolve_authenticated_user_id", lambda *_args, **_kwargs: "redaction_user")

    try:
        with TestClient(_build_mobile_app()) as client:
            response = client.post(
                "/api/v1/assessment/create",
                json={"assessment_type": "diagnostic", "count": 20},
            )
    finally:
        path_service._user_data_dir = original_user_data_dir

    assert response.status_code == 200
    _assert_no_forbidden_pre_submit_keys(response.json())


def test_redaction_guard_fails_on_hidden_answer_fixture() -> None:
    with pytest.raises(AssertionError, match="forbidden key leaked"):
        _assert_no_forbidden_pre_submit_keys(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "answer": "A",
                    }
                ]
            }
        )


def test_redaction_guard_fails_on_structural_grading_fixture() -> None:
    with pytest.raises(AssertionError, match="forbidden key substring leaked"):
        _assert_no_forbidden_pre_submit_keys(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "gradingArtifact": {"expected_choice": "A"},
                    }
                ]
            }
        )
