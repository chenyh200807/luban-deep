"""Stage 5 live qa/operator PGO traffic canary runner tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeAsyncClient:
    def __init__(
        self,
        responses: dict[tuple[str, str], list[_FakeResponse]],
        captured: dict[str, Any],
        **_kwargs: Any,
    ) -> None:
        self._responses = responses
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, *, headers=None, json=None, params=None):
        key = (method.upper(), path)
        self._captured.setdefault("requests", []).append(
            {
                "method": method.upper(),
                "path": path,
                "headers": dict(headers or {}),
                "json": dict(json or {}) if isinstance(json, dict) else json,
                "params": dict(params or {}) if isinstance(params, dict) else params,
            }
        )
        queue = self._responses.get(key) or []
        if not queue:
            raise AssertionError(f"unexpected request: {key}")
        return queue.pop(0)


class _FakeWebSocket:
    def __init__(self, events: list[dict[str, Any]], captured: dict[str, Any]) -> None:
        self._events = [json.dumps(item, ensure_ascii=False) for item in events]
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, raw: str) -> None:
        self._captured.setdefault("ws_payloads", []).append(json.loads(raw))

    async def recv(self) -> str:
        if not self._events:
            raise AssertionError("unexpected ws recv")
        return self._events.pop(0)


def _result_event(*, slot: str, source: str, awarded: float, maximum: float = 5.0) -> list[dict[str, Any]]:
    return [
        {
            "type": "result",
            "metadata": {
                "construction_grading_result": {"type": "case", "score_awarded": awarded, "max_score": maximum},
                "luban_case_rubric_v1": {
                    "authority": "luban_case_rubric_v1",
                    "status": "ok",
                    "official_score_allowed": False,
                    "grading_event": {
                        "event_type": "case_grading_completed",
                        "question_id": "2015::EXAM_XW2015_CASE_1::E0",
                        "rubric_bank_slot": slot,
                        "grading_source": source,
                        "score_authority": (
                            "official_total_x_verdict_coverage"
                            if source == "rubric_scored_pgo"
                            else "legacy_point_sum"
                        ),
                        "awarded_score": awarded,
                        "max_score": maximum,
                        "official_score_allowed": False,
                        "high_risk_review": False,
                    },
                },
            },
        },
        {"type": "done", "metadata": {"status": "completed"}},
    ]


@pytest.mark.asyncio
async def test_live_traffic_canary_reports_pgo_for_qa_operator_and_legacy_control(
    tmp_path: Path,
) -> None:
    from scripts.run_luban_pgo_stage5_live_traffic_canary import run_live_traffic_canary

    out = tmp_path / "live_canary"
    captured: dict[str, Any] = {}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_stage5_pgo_live", "id": "qa_stage5_pgo_live"}),
            _FakeResponse(200, {"user_id": "operator_stage5_pgo_live", "id": "operator_stage5_pgo_live"}),
            _FakeResponse(200, {"user_id": "student_stage5_pgo_live", "id": "student_stage5_pgo_live"}),
        ],
    }
    ws_batches = [
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=5.0),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=2.5),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=5.0),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=2.5),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=4.0),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=1.0),
    ]

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(_url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await run_live_traffic_canary(
        api_base_url="https://test2.example.com",
        out_dir=out,
        qa_auth_token="qa-token",
        operator_auth_token="operator-token",
        noncohort_auth_token="student-token",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        timeout_seconds=10.0,
    )

    assert result["go_no_go"]["status"] == "LIVE_QA_OPERATOR_CANARY_GO"
    assert result["go_no_go"]["blockers"] == []
    assert result["live_canary"]["required_roles_passed"] == {"qa": True, "operator": True}
    assert result["live_canary"]["noncohort_control_passed"] is True
    assert result["shadow_delta"]["sample_count"] == 2
    assert result["score_distribution"]["pgo"]["count"] == 4
    assert result["score_distribution"]["legacy"]["count"] == 2
    assert result["over_credit"]["pgo"]["awarded_gt_max_count"] == 0
    assert captured["ws_payloads"][0]["config"]["followup_question_context"]["question_id"] == (
        "2015::EXAM_XW2015_CASE_1::E0"
    )
    assert (out / "live_canary_report.json").exists()
    assert (out / "live_ws_events.json").exists()


@pytest.mark.asyncio
async def test_live_traffic_canary_blocks_missing_operator_auth(tmp_path: Path) -> None:
    from scripts.run_luban_pgo_stage5_live_traffic_canary import run_live_traffic_canary

    captured: dict[str, Any] = {}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "qa_stage5_pgo_live", "id": "qa_stage5_pgo_live"}),
            _FakeResponse(200, {"user_id": "student_stage5_pgo_live", "id": "student_stage5_pgo_live"}),
        ],
    }
    ws_batches = [
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=5.0),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=2.5),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=4.0),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=1.0),
    ]

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(_url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await run_live_traffic_canary(
        api_base_url="https://test2.example.com",
        out_dir=tmp_path / "missing_operator",
        qa_auth_token="qa-token",
        noncohort_auth_token="student-token",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        timeout_seconds=10.0,
    )

    assert result["go_no_go"]["status"] == "LIVE_QA_OPERATOR_CANARY_BLOCKED"
    assert "operator_auth_material_missing" in result["go_no_go"]["blockers"]
    assert result["live_canary"]["required_roles_passed"] == {"qa": True, "operator": False}


@pytest.mark.asyncio
async def test_live_traffic_canary_does_not_count_spoofed_qa_username_as_role_pass(
    tmp_path: Path,
) -> None:
    from scripts.run_luban_pgo_stage5_live_traffic_canary import run_live_traffic_canary

    captured: dict[str, Any] = {}
    responses = {
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(
                200,
                {
                    "user_id": "004727f5-3b4d-4110-b153-7cb7d08671c8",
                    "id": "004727f5-3b4d-4110-b153-7cb7d08671c8",
                    "username": "qa_stage5_pgo_live",
                },
            ),
            _FakeResponse(200, {"user_id": "operator_stage5_pgo_live", "id": "operator_stage5_pgo_live"}),
            _FakeResponse(200, {"user_id": "student_stage5_pgo_live", "id": "student_stage5_pgo_live"}),
        ],
    }
    ws_batches = [
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=4.0),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=2.0),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=5.0),
        _result_event(slot="pgo", source="rubric_scored_pgo", awarded=2.5),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=4.0),
        _result_event(slot="legacy", source="rubric_scored_v1", awarded=2.0),
    ]

    def _client_factory(**kwargs: Any):
        return _FakeAsyncClient(responses, captured, **kwargs)

    def _connector_factory(_url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), captured)

    result = await run_live_traffic_canary(
        api_base_url="https://test2.example.com",
        out_dir=tmp_path / "spoofed_qa",
        qa_auth_token="qa-token",
        operator_auth_token="operator-token",
        noncohort_auth_token="student-token",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
        timeout_seconds=10.0,
    )

    assert result["go_no_go"]["status"] == "LIVE_QA_OPERATOR_CANARY_BLOCKED"
    assert "qa_authenticated_user_not_canary" in result["go_no_go"]["blockers"]
    assert result["live_canary"]["required_roles_passed"] == {"qa": False, "operator": True}
    assert result["live_canary"]["auth"]["qa"]["role_identity_ok"] is False
