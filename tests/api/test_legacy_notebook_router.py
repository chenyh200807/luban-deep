from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext
from deeptutor.services.notebook.service import NotebookManager

notebook_router_module = importlib.import_module("deeptutor.api.routers.notebook")
router = notebook_router_module.router


def _ctx(user_id: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=False,
    )


def _build_app(tmp_path, user_id: str) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[notebook_router_module.get_current_user] = lambda: _ctx(user_id)
    notebook_router_module.notebook_manager = NotebookManager(base_dir=str(tmp_path / "notebook"))
    app.include_router(router, prefix="/api/v1/notebook")
    return app


def test_legacy_notebook_router_requires_authentication(tmp_path) -> None:
    notebook_router_module.notebook_manager = NotebookManager(base_dir=str(tmp_path / "notebook"))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/notebook")

    with TestClient(app) as client:
        response = client.get("/api/v1/notebook/list")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_legacy_notebook_router_scopes_data_to_authenticated_owner(tmp_path) -> None:
    owner_app = _build_app(tmp_path, "student_a")
    foreign_app = _build_app(tmp_path, "student_b")

    with TestClient(owner_app) as owner_client:
        created = owner_client.post(
            "/api/v1/notebook/create",
            json={"name": "我的错题本", "description": "仅自己可见"},
        )
        assert created.status_code == 200
        notebook_id = created.json()["notebook"]["id"]
        listing = owner_client.get("/api/v1/notebook/list")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()["notebooks"]] == [notebook_id]

    with TestClient(foreign_app) as foreign_client:
        foreign_listing = foreign_client.get("/api/v1/notebook/list")
        assert foreign_listing.status_code == 200
        assert foreign_listing.json()["notebooks"] == []

        foreign_get = foreign_client.get(f"/api/v1/notebook/{notebook_id}")
        assert foreign_get.status_code == 404

        foreign_delete = foreign_client.delete(f"/api/v1/notebook/{notebook_id}")
        assert foreign_delete.status_code == 404
