from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

router = importlib.import_module("deeptutor.api.routers.observability").router
observability_module = importlib.import_module("deeptutor.services.observability")


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/observability")
    return app


@pytest.fixture(autouse=True)
def _reset_observability_stores(tmp_path) -> None:
    observability_module.reset_surface_event_store()
    observability_module.reset_control_plane_store(base_dir=tmp_path / "control_plane")
    yield
    observability_module.reset_surface_event_store()
    observability_module.reset_control_plane_store(base_dir=tmp_path / "control_plane")


def test_surface_event_router_accepts_event_and_updates_coverage_snapshot() -> None:
    app = _build_app()

    with TestClient(app) as client:
        start_response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-start-1",
                "surface": "web",
                "event_name": "start_turn_sent",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "collected_at_ms": 1710000000000,
                "sent_at_ms": 1710000000010,
            },
        )
        render_response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-render-1",
                "surface": "web",
                "event_name": "first_visible_content_rendered",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "collected_at_ms": 1710000000100,
                "sent_at_ms": 1710000000110,
            },
        )

    assert start_response.status_code == 202
    assert start_response.json()["status"] == "accepted"
    assert render_response.status_code == 202
    assert render_response.json()["status"] == "accepted"

    snapshot = observability_module.get_surface_event_store().snapshot()
    assert snapshot["event_counts"] == [
        {
            "surface": "web",
            "event_name": "first_visible_content_rendered",
            "status": "accepted",
            "count": 1,
        },
        {
            "surface": "web",
            "event_name": "start_turn_sent",
            "status": "accepted",
            "count": 1,
        },
    ]
    assert snapshot["coverage"] == [
        {
            "surface": "web",
            "start_turn_sent": 1,
            "first_visible_content_rendered": 1,
            "done_rendered": 0,
            "surface_render_failed": 0,
            "first_render_coverage_ratio": 1.0,
            "done_render_coverage_ratio": 0.0,
        }
    ]


def test_surface_event_router_deduplicates_event_id() -> None:
    app = _build_app()

    payload = {
        "event_id": "evt-dup-1",
        "surface": "wechat_miniprogram",
        "event_name": "done_rendered",
        "session_id": "session-2",
        "turn_id": "turn-2",
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/observability/surface-events", json=payload)
        second = client.post("/api/v1/observability/surface-events", json=payload)

    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"

    snapshot = observability_module.get_surface_event_store().snapshot()
    assert snapshot["event_counts"] == [
        {
            "surface": "wechat_miniprogram",
            "event_name": "done_rendered",
            "status": "accepted",
            "count": 1,
        },
        {
            "surface": "wechat_miniprogram",
            "event_name": "done_rendered",
            "status": "duplicate",
            "count": 1,
        },
    ]


def test_surface_event_router_rejects_unknown_event_name() -> None:
    app = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-invalid-1",
                "surface": "web",
                "event_name": "not_supported",
            },
        )

    assert response.status_code == 400
    assert "Unsupported event_name" in response.json()["detail"]


def test_control_plane_router_returns_latest_and_history() -> None:
    app = _build_app()
    store = observability_module.get_control_plane_store()
    store.write_run(
        kind="arr_runs",
        run_id="arr-lite-1",
        release_id="rel-1",
        payload={"summary": {"pass_rate": 1.0}},
    )

    with TestClient(app) as client:
        latest = client.get("/api/v1/observability/control-plane/arr_runs/latest")
        history = client.get("/api/v1/observability/control-plane/arr_runs/history?limit=5")

    assert latest.status_code == 200
    assert latest.json()["record"]["run_id"] == "arr-lite-1"
    assert history.status_code == 200
    assert len(history.json()["records"]) == 1
