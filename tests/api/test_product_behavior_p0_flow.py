from __future__ import annotations

import importlib
import time

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.observability.surface_events import SurfaceEventStore

observability_router = importlib.import_module("deeptutor.api.routers.observability").router
observability_module = importlib.import_module("deeptutor.services.observability")


def _ctx() -> AuthContext:
    return AuthContext(
        user_id="u_behavior_p0",
        provider="test",
        token="test-token",
        claims={"uid": "u_behavior_p0"},
        is_admin=True,
    )


def test_product_behavior_p0_surface_event_to_member_summary(tmp_path) -> None:
    observability_module.reset_surface_event_store()
    observability_module.reset_product_behavior_store(tmp_path / "behavior.db")
    app = FastAPI()
    app.include_router(observability_router, prefix="/api/v1/observability")
    app.dependency_overrides[get_current_user] = _ctx

    now_ms = int(time.time() * 1000)
    events = [
        (
            "evt-1",
            "module_viewed",
            {"visit_id": "visit-1", "module": "learning_report", "action": "view"},
        ),
        (
            "evt-2",
            "section_viewed",
            {
                "visit_id": "visit-1",
                "module": "learning_report",
                "section": "next_action",
                "action": "view",
            },
        ),
        (
            "evt-3",
            "module_viewed",
            {"visit_id": "visit-2", "module": "history", "action": "view"},
        ),
    ]
    with TestClient(app) as client:
        for event_id, event_name, metadata in events:
            response = client.post(
                "/api/v1/observability/surface-events",
                json={
                    "event_id": event_id,
                    "surface": "web",
                    "event_name": event_name,
                    "collected_at_ms": now_ms,
                    "sent_at_ms": now_ms + 100,
                    "metadata": metadata,
                },
            )
            assert response.status_code == 202

    store = observability_module.get_product_behavior_store()
    summary = store.get_member_behavior_summary("u_behavior_p0", days=7)
    sections = store.get_learning_report_section_breakdown("u_behavior_p0", days=7)

    assert summary["learning_report_open_count_7d"] == 1
    assert summary["history_open_count_7d"] == 1
    assert sections == [{"section": "next_action", "view_count": 1}]


def test_product_behavior_persistence_failure_allows_same_event_id_retry(monkeypatch) -> None:
    attempts = []

    class FlakyStore:
        def record_event(self, event):
            attempts.append(event["event_id"])
            if len(attempts) == 1:
                raise RuntimeError("temporary sqlite failure")
            return {"accepted": True, "status": "accepted", "event_id": event["event_id"]}

    monkeypatch.setattr(observability_module, "get_product_behavior_store", lambda: FlakyStore())
    store = SurfaceEventStore()
    payload = {
        "event_id": "evt-retry-1",
        "surface": "wechat_yousenwebview",
        "event_name": "module_viewed",
        "user_id": "member-1",
        "metadata": {"visit_id": "visit-1", "module": "learning", "action": "view"},
    }

    first = store.ingest(payload)
    second = store.ingest(payload)

    assert first["accepted"] is False
    assert first["status"] == "retryable_persistence_failure"
    assert second["accepted"] is True
    assert second["product_behavior_status"] == "accepted"
    assert attempts == ["evt-retry-1", "evt-retry-1"]
