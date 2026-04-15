from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest
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


def _cors_middleware_options(app: FastAPI) -> dict[str, object]:
    for middleware in app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORS middleware not configured")


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
    }

    degraded = asyncio.run(module.readyz())
    assert degraded.status_code == 503
    degraded_payload = json.loads(degraded.body)
    assert degraded_payload["status"] == "degraded"
    assert degraded_payload["ready"] is False


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
    monkeypatch.setattr(llm_module, "get_llm_client", lambda: _FakeLLMClient())
    monkeypatch.setattr(event_bus_module, "get_event_bus", lambda: _FakeEventBus())
    monkeypatch.setattr(tutorbot_module, "get_tutorbot_manager", lambda: _FakeTutorbotManager())

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
