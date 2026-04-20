from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest
from deeptutor.api.dependencies.auth import AuthContext
from fastapi import Request
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
CORSMiddleware = pytest.importorskip("fastapi.middleware.cors").CORSMiddleware


class _FakePathService:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _dir(self, *parts: str) -> Path:
        path = self._root.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def project_root(self) -> Path:
        return self._root

    def ensure_all_directories(self) -> None:
        self.get_public_outputs_root().mkdir(parents=True, exist_ok=True)
        self.get_settings_dir().mkdir(parents=True, exist_ok=True)
        self.get_logs_dir()
        self.get_workspace_dir()
        self.get_tutor_state_root()
        self.get_notebook_dir()
        self.get_memory_dir()
        self.get_co_writer_dir()
        self.get_guide_dir()
        self.get_chat_dir()
        self.get_solve_dir()
        self.get_question_dir()
        self.get_research_dir()

    def get_chat_history_db(self) -> Path:
        path = self._root / "chat_history.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_public_outputs_root(self) -> Path:
        return self._dir("outputs")

    def get_logs_dir(self) -> Path:
        return self._dir("logs")

    def get_settings_dir(self) -> Path:
        return self._dir("settings")

    def get_user_root(self) -> Path:
        return self._root

    def get_workspace_dir(self) -> Path:
        return self._dir("workspace")

    def get_tutor_state_root(self) -> Path:
        return self._dir("tutor_state")

    def get_learner_state_root(self) -> Path:
        return self._dir("learner_state")

    def get_runtime_dir(self) -> Path:
        return self._dir("data", "runtime")

    def get_learner_state_outbox_db(self) -> Path:
        return self.get_runtime_dir() / "outbox.db"

    def get_notebook_dir(self) -> Path:
        return self._dir("workspace", "notebook")

    def get_memory_dir(self) -> Path:
        return self._dir("memory")

    def get_co_writer_dir(self) -> Path:
        return self._dir("workspace", "co-writer")

    def get_co_writer_history_file(self) -> Path:
        return self.get_co_writer_dir() / "history.json"

    def get_co_writer_tool_calls_dir(self) -> Path:
        return self.get_co_writer_dir() / "tool_calls"

    def get_co_writer_audio_dir(self) -> Path:
        return self.get_co_writer_dir() / "audio"

    def get_guide_dir(self) -> Path:
        return self._dir("workspace", "guide")

    def get_guide_session_file(self, session_id: str) -> Path:
        return self.get_guide_dir() / f"session_{session_id}.json"

    def get_chat_feature_dir(self, feature: str) -> Path:
        return self._dir("workspace", "chat", feature)

    def get_run_code_workspace_dir(self) -> Path:
        return self.get_chat_feature_dir("_detached_code_execution")

    def get_workspace_feature_dir(self, feature: str) -> Path:
        if feature in {"memory", "notebook", "co-writer", "guide"}:
            return self._dir("workspace", feature)
        if feature == "chat":
            return self._dir("workspace", "chat")
        raise ValueError(feature)

    def get_task_workspace(self, feature: str, task_id: str) -> Path:
        return self.get_workspace_feature_dir(feature) / task_id

    def get_session_workspace(self, feature: str, session_id: str) -> Path:
        return self.get_workspace_feature_dir(feature) / session_id

    def get_task_dir(self, module: str, task_id: str) -> Path:
        return self.get_agent_dir(module) / task_id

    def get_session_file(self, module: str) -> Path:
        return self.get_agent_dir(module) / "sessions.json"

    def get_agent_dir(self, module: str) -> Path:
        mapping = {
            "solve": ("workspace", "chat", "deep_solve"),
            "chat": ("workspace", "chat", "chat"),
            "question": ("workspace", "chat", "deep_question"),
            "research": ("workspace", "chat", "deep_research"),
            "math_animator": ("workspace", "chat", "math_animator"),
            "co-writer": ("workspace", "co-writer"),
            "guide": ("workspace", "guide"),
            "run_code_workspace": ("workspace", "chat", "_detached_code_execution"),
            "logs": ("logs",),
        }
        if module not in mapping:
            raise ValueError(module)
        return self._dir(*mapping[module])

    def get_chat_dir(self) -> Path:
        return self.get_chat_feature_dir("chat")

    def get_solve_dir(self) -> Path:
        return self.get_chat_feature_dir("deep_solve")

    def get_question_dir(self) -> Path:
        return self.get_chat_feature_dir("deep_question")

    def get_research_dir(self) -> Path:
        return self.get_chat_feature_dir("deep_research")

    def get_research_reports_dir(self) -> Path:
        return self._dir("workspace", "chat", "deep_research", "reports")

    def get_settings_file(self, name: str) -> Path:
        if "." not in name:
            name = f"{name}.json"
        return self.get_settings_dir() / name

    def get_runtime_config_file(self, name: str) -> Path:
        if not name.endswith(".yaml"):
            name = f"{name}.yaml"
        return self.get_settings_dir() / name


def _reload_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    env: dict[str, str | None],
    tmp_path: Path,
) -> object:
    fake_path_service = _FakePathService(tmp_path)
    path_service_module = importlib.import_module("deeptutor.services.path_service")
    setup_module = importlib.import_module("deeptutor.services.setup")
    sqlite_store_module = importlib.import_module("deeptutor.services.session.sqlite_store")
    monkeypatch.setattr(path_service_module, "get_path_service", lambda: fake_path_service)
    monkeypatch.setattr(setup_module, "init_user_directories", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sqlite_store_module, "get_path_service", lambda: fake_path_service)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    module = importlib.import_module("deeptutor.api.main")
    return importlib.reload(module)


def _install_fake_startup_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeLLMClient:
        class config:
            model = "test-model"

    class _FakeEventBus:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    class _FakeTutorbotManager:
        async def auto_start_bots(self) -> None:
            return None

        async def stop_all(self) -> None:
            return None

    llm_module = importlib.import_module("deeptutor.services.llm")
    event_bus_module = importlib.import_module("deeptutor.events.event_bus")
    tutorbot_module = importlib.import_module("deeptutor.services.tutorbot")
    main_module = importlib.import_module("deeptutor.api.main")

    class _FakeLearnerStateRuntime:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(llm_module, "get_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setattr(event_bus_module, "get_event_bus", lambda: _FakeEventBus())
    monkeypatch.setattr(tutorbot_module, "get_tutorbot_manager", lambda: _FakeTutorbotManager())
    monkeypatch.setattr(main_module, "create_default_learner_state_runtime", lambda _path_service=None: _FakeLearnerStateRuntime())


def _install_failing_startup_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm_error: str | None = None,
) -> None:
    class _FakeEventBus:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    class _FakeTutorbotManager:
        async def auto_start_bots(self) -> None:
            return None

        async def stop_all(self) -> None:
            return None

    llm_module = importlib.import_module("deeptutor.services.llm")
    event_bus_module = importlib.import_module("deeptutor.events.event_bus")
    tutorbot_module = importlib.import_module("deeptutor.services.tutorbot")
    main_module = importlib.import_module("deeptutor.api.main")

    class _FakeLearnerStateRuntime:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    if llm_error is not None:
        monkeypatch.setattr(
            llm_module,
            "get_llm_client",
            lambda: (_ for _ in ()).throw(RuntimeError(llm_error)),
        )
    monkeypatch.setattr(event_bus_module, "get_event_bus", lambda: _FakeEventBus())
    monkeypatch.setattr(tutorbot_module, "get_tutorbot_manager", lambda: _FakeTutorbotManager())
    monkeypatch.setattr(main_module, "create_default_learner_state_runtime", lambda _path_service=None: _FakeLearnerStateRuntime())


def _cors_middleware_options(app: FastAPI) -> dict[str, object]:
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORS middleware not configured")


def _route_paths(app: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "") or "") for route in app.routes}


def test_cors_defaults_to_safe_origins_in_non_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )

    options = _cors_middleware_options(module.app)
    assert options["allow_credentials"] is True
    assert options["allow_origins"] == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3782",
        "http://127.0.0.1:3782",
    ]


def test_cors_uses_env_allowlist_and_ignores_wildcard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "production",
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": "https://admin.example.com, *, https://app.example.com, https://admin.example.com",
        },
        tmp_path=tmp_path,
    )

    options = _cors_middleware_options(module.app)
    assert options["allow_credentials"] is True
    assert options["allow_origins"] == [
        "https://admin.example.com",
        "https://app.example.com",
    ]


def test_production_disables_legacy_router_mounts_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "production",
            "DEEPTUTOR_ENABLE_LEGACY_ROUTERS": None,
        },
        tmp_path=tmp_path,
    )

    paths = _route_paths(module.app)
    assert "/api/v1/ws" in paths
    assert "/api/v1/sessions" in paths
    assert "/api/outputs" not in paths
    assert "/api/v1/solve" not in paths
    assert "/api/v1/chat" not in paths
    assert "/api/v1/question/mimic" not in paths
    assert "/api/v1/dashboard/recent" not in paths
    assert "/api/v1/notebook/list" not in paths
    assert "/api/v1/plugins/list" not in paths
    assert "/api/v1/tutorbot" not in paths


def test_public_outputs_can_be_explicitly_reenabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "production",
            "DEEPTUTOR_ENABLE_PUBLIC_OUTPUTS": "1",
        },
        tmp_path=tmp_path,
    )

    paths = _route_paths(module.app)
    assert "/api/outputs" in paths


def test_legacy_router_flag_explicitly_reenables_compatibility_mounts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "production",
            "DEEPTUTOR_ENABLE_LEGACY_ROUTERS": "1",
        },
        tmp_path=tmp_path,
    )

    paths = _route_paths(module.app)
    assert "/api/v1/solve" in paths
    assert "/api/v1/chat" not in paths
    assert "/api/v1/question/mimic" in paths
    assert "/api/v1/dashboard/recent" in paths
    assert "/api/v1/notebook/list" in paths


def test_readyz_reflects_readiness_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    module.app.state.readiness_checks = {
        "config_consistent": True,
        "llm_client_ready": True,
        "event_bus_ready": True,
        "tutorbots_ready": True,
        "learner_state_runtime_ready": True,
    }

    response = asyncio.run(module.readyz())
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["status"] == "ok"
    assert payload["ready"] is True

    module.app.state.readiness_checks = {
        "config_consistent": True,
        "llm_client_ready": False,
        "event_bus_ready": True,
        "tutorbots_ready": True,
        "learner_state_runtime_ready": True,
    }

    degraded = asyncio.run(module.readyz())
    assert degraded.status_code == 503
    degraded_payload = json.loads(degraded.body)
    assert degraded_payload["status"] == "degraded"
    assert degraded_payload["ready"] is False


def test_production_startup_fails_fast_when_critical_dependency_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "production",
            "DEEPTUTOR_STARTUP_FAIL_FAST": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_failing_startup_dependencies(monkeypatch, llm_error="llm boom")

    with pytest.raises(RuntimeError, match="Critical startup dependencies failed: llm_client_ready: llm boom"):
        with TestClient(module.app):
            pass


def test_local_startup_keeps_process_alive_when_fail_fast_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "DEEPTUTOR_STARTUP_FAIL_FAST": "0",
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_failing_startup_dependencies(monkeypatch, llm_error="llm boom")

    with TestClient(module.app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["llm_client_ready"] is False
    assert payload["checks"]["learner_state_runtime_ready"] is True


def test_startup_and_shutdown_manage_learner_state_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)

    runtime_calls = {"start": 0, "stop": 0}

    class _TrackingRuntime:
        async def start(self) -> None:
            runtime_calls["start"] += 1

        async def stop(self) -> None:
            runtime_calls["stop"] += 1

    monkeypatch.setattr(module, "create_default_learner_state_runtime", lambda _path_service=None: _TrackingRuntime())

    with TestClient(module.app):
        pass

    assert runtime_calls == {"start": 1, "stop": 1}
    assert module.app.state.readiness_checks["learner_state_runtime_ready"] is True


def test_http_request_id_is_echoed_and_bound_to_request_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)

    @module.app.get("/_request_id_probe", include_in_schema=False)
    async def _request_id_probe(request: Request):
        return {"request_id": getattr(request.state, "request_id", "")}

    with TestClient(module.app) as client:
        echoed = client.get("/_request_id_probe", headers={"X-Request-ID": "req-123"})
        generated = client.get("/_request_id_probe")

    assert echoed.status_code == 200
    assert echoed.headers["X-Request-ID"] == "req-123"
    assert echoed.json()["request_id"] == "req-123"

    assert generated.status_code == 200
    assert generated.headers["X-Request-ID"]
    assert generated.headers["X-Request-ID"] == generated.json()["request_id"]
    assert generated.headers["X-Request-ID"] != "req-123"


def test_healthz_and_metrics_expose_runtime_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)
    module.app.state.readiness_checks = {
        "config_consistent": True,
        "llm_client_ready": True,
        "event_bus_ready": True,
        "tutorbots_ready": True,
    }
    module.app.dependency_overrides[module.require_metrics_access] = lambda: None

    error_rate_module = importlib.import_module("deeptutor.utils.error_rate_tracker")
    circuit_breaker_module = importlib.import_module("deeptutor.utils.network.circuit_breaker")
    error_rate_module.clear_tracker_state()
    circuit_breaker_module.reset_circuit_breakers()
    error_rate_module.record_provider_call("test-provider", success=False)
    circuit_breaker_module.record_call_failure("test-provider")

    @module.app.get("/_metrics_probe", include_in_schema=False)
    async def _metrics_probe():
        return {"ok": True}

    with TestClient(module.app) as client:
        health = client.get("/healthz")
        probe = client.get("/_metrics_probe")
        missing = client.get("/does-not-exist")
        metrics = client.get("/metrics")

    assert health.status_code == 200
    assert health.json()["alive"] is True
    assert health.json()["uptime_seconds"] >= 0

    assert probe.status_code == 200
    assert missing.status_code == 404

    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["readiness"]["ready"] is True
    assert payload["http"]["requests_total"] >= 3
    assert any(route["route"] == "GET /_metrics_probe" for route in payload["http"]["routes"])
    assert "404" in payload["http"]["status_counts"]
    assert payload["providers"]["error_rates"]["test-provider"]["error_calls"] >= 1
    assert payload["providers"]["circuit_breakers"]["test-provider"]["failure_count"] >= 1
    error_rate_module.clear_tracker_state()
    circuit_breaker_module.reset_circuit_breakers()


def test_metrics_prometheus_exports_runtime_and_provider_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)
    module.app.state.readiness_checks = {
        "config_consistent": True,
        "llm_client_ready": True,
        "event_bus_ready": True,
        "tutorbots_ready": True,
    }
    module.app.dependency_overrides[module.require_metrics_access] = lambda: None

    error_rate_module = importlib.import_module("deeptutor.utils.error_rate_tracker")
    circuit_breaker_module = importlib.import_module("deeptutor.utils.network.circuit_breaker")
    error_rate_module.clear_tracker_state()
    circuit_breaker_module.reset_circuit_breakers()
    error_rate_module.record_provider_call("test-provider", success=False)
    circuit_breaker_module.record_call_failure("test-provider")

    @module.app.get("/_prometheus_probe", include_in_schema=False)
    async def _prometheus_probe():
        return {"ok": True}

    with TestClient(module.app) as client:
        client.get("/_prometheus_probe")
        metrics = client.get("/metrics/prometheus")

    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    body = metrics.text
    assert "deeptutor_ready 1" in body
    assert 'deeptutor_http_requests_total ' in body
    assert 'deeptutor_http_route_requests_total{route="GET /_prometheus_probe"}' in body
    assert 'deeptutor_provider_error_rate{provider="test-provider"}' in body
    assert 'deeptutor_provider_threshold_exceeded{provider="test-provider"} 1' in body
    assert 'deeptutor_circuit_breaker_failure_count{provider="test-provider"}' in body
    error_rate_module.clear_tracker_state()
    circuit_breaker_module.reset_circuit_breakers()


@pytest.mark.parametrize(("path"), ("/metrics", "/metrics/prometheus"))
def test_metrics_endpoints_require_admin_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)

    with TestClient(module.app) as client:
        unauthenticated = client.get(path)

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "Authentication required"

    auth_module = importlib.import_module("deeptutor.api.dependencies.auth")
    monkeypatch.setattr(
        auth_module,
        "resolve_auth_context",
        lambda _authorization: AuthContext(
            user_id="student_demo",
            provider="test",
            token="test-token",
            claims={"uid": "student_demo"},
            is_admin=False,
        ),
    )

    with TestClient(module.app) as client:
        forbidden = client.get(path)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Admin access required"


@pytest.mark.parametrize(("path"), ("/metrics", "/metrics/prometheus"))
def test_metrics_endpoints_accept_dedicated_metrics_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
) -> None:
    module = _reload_main(
        monkeypatch,
        env={
            "DEEPTUTOR_ENV": "local",
            "APP_ENV": None,
            "ENV": None,
            "ENVIRONMENT": None,
            "DEEPTUTOR_CORS_ALLOW_ORIGINS": None,
            "DEEPTUTOR_METRICS_TOKEN": "metrics-secret",
        },
        tmp_path=tmp_path,
    )
    monkeypatch.setattr(module, "validate_tool_consistency", lambda: None)
    _install_fake_startup_dependencies(monkeypatch)

    with TestClient(module.app) as client:
        response = client.get(path, headers={"X-Metrics-Token": "metrics-secret"})

    assert response.status_code == 200
