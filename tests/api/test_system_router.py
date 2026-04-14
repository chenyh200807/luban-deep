from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
system_module = importlib.import_module("deeptutor.api.routers.system")
router = system_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_turn_contract_endpoint_exposes_unified_schema() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/turn-contract")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["transport"]["primary_websocket"] == "/api/v1/ws"
    assert "start_turn_message" in body["schemas"]
    assert "turn_start_response" in body["schemas"]
    assert "bot_id" in body["trace_fields"]
    assert body["docs"]["contract"] == "/CONTRACT.md"
    assert body["docs"]["guide"] == "/docs/zh/guide/unified-turn-contract.md"


def test_contracts_index_endpoint_exposes_domain_map() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/contracts-index")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["entrypoint"] == "CONTRACT.md"
    assert "turn" in body["domains"]
    assert "capability" in body["domains"]
    assert "rag" in body["domains"]
    assert "config_runtime" in body["domains"]
    assert "deeptutor/api/routers/unified_ws.py" in body["domains"]["turn"]["protected_patterns"]


def test_runtime_topology_declares_ws_as_single_stream_entry() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/runtime-topology")

    assert response.status_code == 200
    body = response.json()
    assert body["primary_runtime"]["transport"] == "/api/v1/ws"
    assert {"router": "mobile", "mode": "http_bootstrap_adapter"} in body["compatibility_routes"]
    assert all(
        route["mode"] != "streaming_adapter" for route in body["compatibility_routes"]
    )
