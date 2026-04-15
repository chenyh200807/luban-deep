from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional dependency in lightweight envs
    FastAPI = None
    TestClient = None

pytestmark = pytest.mark.skipif(FastAPI is None or TestClient is None, reason="fastapi not installed")

if FastAPI is not None and TestClient is not None:
    knowledge_router_module = importlib.import_module("deeptutor.api.routers.knowledge")
    router = knowledge_router_module.router
else:  # pragma: no cover - optional dependency in lightweight envs
    knowledge_router_module = None
    router = None


def _build_app(admin: bool = True) -> FastAPI:
    if FastAPI is None or router is None:  # pragma: no cover - guarded by pytestmark
        raise RuntimeError("fastapi is not installed")
    app = FastAPI()
    if admin:
        app.dependency_overrides[knowledge_router_module.require_admin] = lambda: None
    app.include_router(router, prefix="/api/v1/knowledge")
    return app


class _FakeKBManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.base_dir / "kb_config.json"
        self.config: dict[str, dict] = {"knowledge_bases": {}}

    def _load_config(self) -> dict:
        return self.config

    def _save_config(self) -> None:
        pass

    def list_knowledge_bases(self) -> list[str]:
        return sorted(self.config.get("knowledge_bases", {}).keys())

    def update_kb_status(self, name: str, status: str, progress: dict | None = None) -> None:
        entry = self.config.setdefault("knowledge_bases", {}).setdefault(name, {"path": name})
        entry["status"] = status
        entry["progress"] = progress or {}

    def get_knowledge_base_path(self, name: str) -> Path:
        kb_dir = self.base_dir / name
        kb_dir.mkdir(parents=True, exist_ok=True)
        return kb_dir

    def link_folder(self, kb_name: str, folder_path: str) -> dict:
        folder = Path(folder_path).expanduser().resolve()
        kb_dir = self.get_knowledge_base_path(kb_name)
        metadata_file = kb_dir / "metadata.json"
        metadata: dict = {"linked_folders": []}
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        linked_folders = metadata.setdefault("linked_folders", [])

        folder_id = hashlib.md5(str(folder).encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324
        for item in linked_folders:
            if item.get("id") == folder_id:
                return item

        folder_info = {
            "id": folder_id,
            "path": str(folder),
            "added_at": "2026-01-01T00:00:00",
            "file_count": len([item for item in folder.rglob("*") if item.is_file()]),
        }
        linked_folders.append(folder_info)
        metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return folder_info


class _FakeInitializer:
    def __init__(self, kb_name: str, base_dir: str, **_kwargs) -> None:
        self.kb_name = kb_name
        self.base_dir = base_dir
        self.kb_dir = Path(base_dir) / kb_name
        self.raw_dir = self.kb_dir / "raw"
        self.progress_tracker = _kwargs.get("progress_tracker")

    def create_directory_structure(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _register_to_config(self) -> None:
        pass


def _upload_payload() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", ("demo.txt", b"hello", "text/plain"))]


def test_rag_providers_returns_registered_backends() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/knowledge/rag-providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "providers": [
            {
                "id": "llamaindex",
                "name": "LlamaIndex",
                "description": "Pure vector retrieval, fastest processing speed.",
            },
            {
                "id": "supabase",
                "name": "Supabase",
                "description": "Read-only remote retrieval powered by your Supabase knowledge base.",
            },
        ]
    }


def test_rag_providers_runtime_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomService:
        @staticmethod
        def list_providers() -> list[dict]:
            raise RuntimeError("internal provider failure secret")

    rag_service_module = importlib.import_module("deeptutor.services.rag.service")
    monkeypatch.setattr(rag_service_module, "RAGService", _BoomService)

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/knowledge/rag-providers")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail == "Failed to fetch RAG providers. Please try again later."
    assert "internal provider failure secret" not in detail


def test_create_kb_does_not_require_llm_precheck(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    monkeypatch.setattr(knowledge_router_module, "KnowledgeBaseInitializer", _FakeInitializer)
    monkeypatch.setattr(knowledge_router_module, "get_llm_config", lambda: (_ for _ in ()).throw(RuntimeError("should not be called")), raising=False)

    async def _noop_init_task(*_args, **_kwargs):
        return None

    monkeypatch.setattr(knowledge_router_module, "run_initialization_task", _noop_init_task)
    monkeypatch.setattr(knowledge_router_module, "_kb_base_dir", tmp_path / "knowledge_bases")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/create",
            data={"name": "kb-new", "rag_provider": "llamaindex"},
            files=_upload_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "kb-new"
    assert isinstance(body.get("task_id"), str) and body["task_id"]
    assert manager.config["knowledge_bases"]["kb-new"]["rag_provider"] == "llamaindex"
    assert manager.config["knowledge_bases"]["kb-new"]["needs_reindex"] is False


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/api/v1/knowledge/demo/link-folder", {"json": {"folder_path": "/tmp/demo"}}),
        ("get", "/api/v1/knowledge/demo/linked-folders", {}),
        ("delete", "/api/v1/knowledge/demo/linked-folders/folder-1", {}),
        ("post", "/api/v1/knowledge/demo/sync-folder/folder-1", {}),
    ],
)
def test_link_folder_routes_require_admin(method: str, path: str, kwargs: dict) -> None:
    with TestClient(_build_app(admin=False)) as client:
        response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401


def test_create_rejects_unregistered_provider(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    monkeypatch.setattr(knowledge_router_module, "_kb_base_dir", tmp_path / "knowledge_bases")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/create",
            data={"name": "kb-invalid", "rag_provider": "lightrag"},
            files=_upload_payload(),
        )

    assert response.status_code == 400
    assert "Unsupported RAG provider" in response.json()["detail"]


def test_link_folder_rejects_paths_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    allowed_folder = allowed_root / "notes"
    allowed_folder.mkdir()
    blocked_folder = tmp_path / "blocked"
    blocked_folder.mkdir()

    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    manager.config["knowledge_bases"]["kb-safe"] = {
        "path": "kb-safe",
        "rag_provider": "llamaindex",
        "needs_reindex": False,
        "status": "ready",
    }
    manager.get_knowledge_base_path("kb-safe")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    monkeypatch.setenv("DEEPTUTOR_KNOWLEDGE_FOLDER_ROOTS", str(allowed_root))

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/kb-safe/link-folder",
            json={"folder_path": str(blocked_folder)},
        )

    assert response.status_code == 400
    assert "allowed root" in response.json()["detail"].lower()

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/kb-safe/link-folder",
            json={"folder_path": str(allowed_folder)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(allowed_folder.resolve())
    assert body["id"]


def test_sync_folder_rejects_unsafe_historical_path(monkeypatch, tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    blocked_folder = tmp_path / "blocked"
    blocked_folder.mkdir()

    class _UnsafeFolderKBManager(_FakeKBManager):
        def get_linked_folders(self, kb_name: str) -> list[dict]:
            return [
                {
                    "id": "folder-1",
                    "path": str(blocked_folder),
                    "added_at": "2026-01-01T00:00:00",
                    "file_count": 0,
                }
            ]

        def detect_folder_changes(self, *_args, **_kwargs) -> dict:
            raise AssertionError("detect_folder_changes should not be called for unsafe paths")

    manager = _UnsafeFolderKBManager(tmp_path / "knowledge_bases")
    manager.config["knowledge_bases"]["kb-safe"] = {
        "path": "kb-safe",
        "rag_provider": "llamaindex",
        "needs_reindex": False,
        "status": "ready",
    }
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    monkeypatch.setenv("DEEPTUTOR_KNOWLEDGE_FOLDER_ROOTS", str(allowed_root))

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/knowledge/kb-safe/sync-folder/folder-1")

    assert response.status_code == 400
    assert "allowed root" in response.json()["detail"].lower()


def test_upload_returns_409_when_kb_needs_reindex(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    manager.config["knowledge_bases"]["legacy-kb"] = {
        "path": "legacy-kb",
        "rag_provider": "llamaindex",
        "needs_reindex": True,
        "status": "needs_reindex",
    }
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/knowledge/legacy-kb/upload", files=_upload_payload())

    assert response.status_code == 409
    assert "needs reindex" in response.json()["detail"].lower()


def test_upload_ready_kb_returns_task_id(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    manager.config["knowledge_bases"]["ready-kb"] = {
        "path": "ready-kb",
        "rag_provider": "llamaindex",
        "needs_reindex": False,
        "status": "ready",
    }
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    monkeypatch.setattr(knowledge_router_module, "_kb_base_dir", tmp_path / "knowledge_bases")

    async def _noop_upload_task(*_args, **_kwargs):
        return None

    monkeypatch.setattr(knowledge_router_module, "run_upload_processing_task", _noop_upload_task)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/knowledge/ready-kb/upload", files=_upload_payload())

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("task_id"), str) and body["task_id"]


def test_update_config_rejects_unregistered_provider() -> None:
    class _FakeConfigService:
        def set_kb_config(self, kb_name: str, config: dict) -> None:
            self.kb_name = kb_name
            self.config = config

        def get_kb_config(self, _kb_name: str) -> dict:
            return {"rag_provider": "llamaindex"}

    fake_service = _FakeConfigService()

    config_module = importlib.import_module("deeptutor.services.config")
    app = _build_app()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(config_module, "get_kb_config_service", lambda: fake_service)
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/knowledge/demo/config",
                json={"rag_provider": "raganything"},
            )

    assert response.status_code == 400
    assert "Unsupported RAG provider" in response.json()["detail"]
