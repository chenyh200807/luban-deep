from __future__ import annotations

import asyncio

from deeptutor.services.observability.unified_ws_smoke import run_unified_ws_smoke


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
    assert result["messages"][0]["type"] == "stage_start"
    assert result["sent_payload"]["type"] == "start_turn"
    assert metrics_calls == ["http://127.0.0.1:8001"]

