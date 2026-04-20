from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
from deeptutor.api.dependencies import AuthContext, get_current_user
system_module = importlib.import_module("deeptutor.api.routers.system")
rate_limit_module = importlib.import_module("deeptutor.api.dependencies.rate_limit")
router = system_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    rate_limit_module.clear_rate_limit_state()
    yield
    rate_limit_module.clear_rate_limit_state()


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


def test_turn_contract_endpoint_exposes_unified_schema() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/turn-contract")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["transport"]["primary_websocket"] == "/api/v1/ws"
    assert "start_turn_message" in body["schemas"]
    assert "turn_start_response" in body["schemas"]
    assert "turn_stream_event" in body["schemas"]
    assert "release_id" in body["trace_fields"]
    assert "git_sha" in body["trace_fields"]
    assert "service_version" in body["trace_fields"]
    assert "deployment_environment" in body["trace_fields"]
    assert "prompt_version" in body["trace_fields"]
    assert "ff_snapshot_hash" in body["trace_fields"]
    assert "bot_id" in body["trace_fields"]
    assert "execution_engine" in body["trace_fields"]
    assert "tool_calls" in body["trace_fields"]
    assert "sources" in body["trace_fields"]
    assert "authority_applied" in body["trace_fields"]
    assert "context_route" in body["trace_fields"]
    assert "task_anchor_type" in body["trace_fields"]
    assert "escalation_level" in body["trace_fields"]
    assert "semantic_router_mode" in body["trace_fields"]
    assert "semantic_router_shadow_route" in body["trace_fields"]
    assert "semantic_router_selected_capability" in body["trace_fields"]
    assert "loaded_sources" in body["trace_fields"]
    assert "token_budget_total" in body["trace_fields"]
    assert "visibility" in body["trace_fields"]
    assert "assistant_content_source" in body["trace_fields"]
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
    assert "learner_state" in body["domains"]
    assert "deeptutor/api/routers/unified_ws.py" in body["domains"]["turn"]["protected_patterns"]
    assert "deeptutor/contracts/learner_state.py" in body["domains"]["learner_state"]["schema_files"]


def test_learner_state_contract_endpoint_exposes_user_id_scoped_state() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/learner-state-contract")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["subject"] == "learner_state"
    assert body["control_surface"]["primary_key"] == "user_id"
    assert body["control_surface"]["summary_truth"] == "learner_summaries"
    assert "user_profiles" in {table["name"] for table in body["tables"]["reused"]}
    assert "learner_summaries" in {table["name"] for table in body["tables"]["new"]}
    assert "bot_learner_overlays" in {table["name"] for table in body["tables"]["phase_2_reserved"]}
    assert "TutorBot workspace memory must not override learner state truth" in body["invariants"]
    assert (
        "phase 2 overlay, if introduced, must remain local and subordinate to learner state truth"
        in body["invariants"]
    )
    assert body["docs"]["contract"] == "/contracts/learner-state.md"
    assert body["docs"]["service_design"] == "/doc/plan/2026-04-15-learner-state-service-design.md"
    assert body["docs"]["overlay_prd"] == "/doc/plan/2026-04-15-bot-learner-overlay-prd.md"


def test_runtime_topology_declares_ws_as_single_stream_entry() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/runtime-topology")

    assert response.status_code == 200
    body = response.json()
    assert body["primary_runtime"]["transport"] == "/api/v1/ws"
    assert {"router": "mobile", "mode": "http_bootstrap_adapter"} in body["compatibility_routes"]
    assert {"router": "tutorbot", "mode": "management_http_only"} in body["compatibility_routes"]
    assert body["deprecated_routes"] == []
    assert all(
        route["mode"] != "streaming_adapter" for route in body["compatibility_routes"]
    )


def test_system_status_requires_admin() -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/status")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_system_llm_test_rate_limits_per_route_and_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    monkeypatch.setattr(
        rate_limit_module,
        "_RATE_LIMIT_POLICY_OVERRIDES",
        {
            "system_test": rate_limit_module.RateLimitPolicy(
                max_requests=1,
                window_seconds=60.0,
            )
        },
    )
    monkeypatch.setattr(
        system_module,
        "get_llm_config",
        lambda: SimpleNamespace(
            model="test-model",
            base_url="http://localhost/v1",
            api_key="test-key",
            binding="local",
        ),
    )
    monkeypatch.setattr(system_module, "get_token_limit_kwargs", lambda _model, max_tokens: {"max_tokens": max_tokens})

    async def _fake_complete(**_kwargs):
        return "OK"

    monkeypatch.setattr(system_module, "llm_complete", _fake_complete)

    with TestClient(app) as client:
        first = client.post("/api/v1/test/llm")
        second = client.post("/api/v1/test/llm")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"
