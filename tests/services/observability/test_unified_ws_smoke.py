from __future__ import annotations

import asyncio
import httpx

from deeptutor.services.observability.unified_ws_smoke import run_unified_ws_smoke
from deeptutor.services.observability.unified_ws_smoke import verify_eval_runner_identity


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self._messages = [
            {"type": "stage_start", "turn_id": "turn-1", "content": "", "session_id": "session-1"},
            {"type": "content", "turn_id": "turn-1", "content": "ok", "session_id": "session-1"},
            {"type": "done", "turn_id": "turn-1", "content": "", "session_id": "session-1"},
        ]

    async def send(self, payload: str) -> None:
        import json

        self.sent_messages.append(json.loads(payload))

    async def recv(self) -> str:
        import json

        if not self._messages:
            raise RuntimeError("no more messages")
        return json.dumps(self._messages.pop(0))


class _FakeConnector:
    def __init__(self) -> None:
        self.websocket = _FakeWebSocket()

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ProfileResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://runtime.example/api/v1/auth/profile")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("profile failed", request=self.request, response=httpx.Response(self.status_code, request=self.request))

    def json(self) -> dict:
        return self._payload


class _ProfileClient:
    response = _ProfileResponse({})

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url: str, *, headers: dict) -> _ProfileResponse:
        assert headers["Authorization"].startswith("Bearer ")
        return self.response


def test_verify_eval_runner_identity_uses_target_profile_authority(monkeypatch) -> None:
    monkeypatch.setattr("deeptutor.services.observability.unified_ws_smoke.httpx.AsyncClient", _ProfileClient)
    _ProfileClient.response = _ProfileResponse(
        {
            "auth_username": "qa_eval_observer",
            "account_kind": "eval_runner",
            "actor_type": "machine",
            "created_by": "eval_runner",
            "is_internal_test": True,
        }
    )
    verified = asyncio.run(
        verify_eval_runner_identity(api_base_url="https://runtime.example", auth_token="token")
    )
    assert verified["verified"] is True

    _ProfileClient.response = _ProfileResponse(
        {
            "auth_username": "student_1",
            "account_kind": "student",
            "actor_type": "human",
            "created_by": "signup",
            "is_internal_test": False,
        }
    )
    rejected = asyncio.run(
        verify_eval_runner_identity(api_base_url="https://runtime.example", auth_token="token")
    )
    assert rejected["verified"] is False
    assert rejected["reason"] == "identity_not_eval_runner"


def test_verify_eval_runner_identity_defers_on_profile_failure(monkeypatch) -> None:
    monkeypatch.setattr("deeptutor.services.observability.unified_ws_smoke.httpx.AsyncClient", _ProfileClient)
    _ProfileClient.response = _ProfileResponse({}, status_code=401)
    result = asyncio.run(
        verify_eval_runner_identity(api_base_url="https://runtime.example", auth_token="token")
    )
    assert result["verified"] is False
    assert result["reason"] == "profile_unavailable"


def test_run_unified_ws_smoke_collects_events_and_metrics(monkeypatch) -> None:
    metrics_calls: list[str] = []

    async def fake_load_metrics(*, api_base_url: str) -> dict:
        metrics_calls.append(api_base_url)
        return {
            "turn_runtime": {
                "turns_started_total": 3,
                "turns_completed_total": 3,
                "turns_failed_total": 0,
                "turns_cancelled_total": 0,
                "turns_in_flight": 0,
            }
        }

    monkeypatch.setattr(
        "deeptutor.services.observability.unified_ws_smoke.load_metrics_snapshot_async",
        fake_load_metrics,
    )

    result = asyncio.run(
        run_unified_ws_smoke(
            api_base_url="http://127.0.0.1:8001",
            message="请回复 ok",
            connector_factory=lambda _url: _FakeConnector(),
        )
    )

    assert result["passed"] is True
    assert result["terminal_event"]["type"] == "done"
    assert result["metrics_after"]["turn_runtime"]["turns_started_total"] == 3
    assert result["metrics_capture"]["ok"] is True
    assert result["metrics_capture"]["status_code"] == 200
    assert result["messages"][0]["type"] == "stage_start"
    assert result["sent_payload"]["type"] == "start_turn"
    assert metrics_calls == ["http://127.0.0.1:8001"]


def test_run_unified_ws_smoke_keeps_ws_success_when_metrics_capture_fails(monkeypatch) -> None:
    async def fake_load_metrics(*, api_base_url: str) -> dict:
        request = httpx.Request("GET", f"{api_base_url.rstrip('/')}/metrics")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("metrics not exposed", request=request, response=response)

    monkeypatch.setattr(
        "deeptutor.services.observability.unified_ws_smoke.load_metrics_snapshot_async",
        fake_load_metrics,
    )

    result = asyncio.run(
        run_unified_ws_smoke(
            api_base_url="https://test2.yousenjiaoyu.com",
            message="请回复 ok",
            connector_factory=lambda _url: _FakeConnector(),
        )
    )

    assert result["passed"] is True
    assert result["terminal_event"]["type"] == "done"
    assert result["metrics_after"] is None
    assert result["metrics_capture"]["ok"] is False
    assert result["metrics_capture"]["status_code"] == 404
    assert "metrics not exposed" in result["metrics_capture"]["error"]


def test_run_unified_ws_smoke_sends_bearer_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_load_metrics(*, api_base_url: str) -> dict:
        return {"turn_runtime": {}}

    def fake_connect(url: str, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("additional_headers")
        return _FakeConnector()

    monkeypatch.setattr(
        "deeptutor.services.observability.unified_ws_smoke.load_metrics_snapshot_async",
        fake_load_metrics,
    )
    monkeypatch.setattr("deeptutor.services.observability.unified_ws_smoke.websockets.connect", fake_connect)

    result = asyncio.run(
        run_unified_ws_smoke(
            api_base_url="http://127.0.0.1:8001",
            message="请回复 ok",
            auth_token="demo-token-student_demo",
        )
    )

    assert result["passed"] is True
    assert result["auth_configured"] is True
    assert captured["url"] == "ws://127.0.0.1:8001/api/v1/ws"
    assert captured["headers"] == {"Authorization": "Bearer demo-token-student_demo"}
