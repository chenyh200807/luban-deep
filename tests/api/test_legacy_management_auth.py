from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.mark.parametrize(
    ("module_name", "prefix", "method", "path"),
    [
        ("deeptutor.api.routers.dashboard", "/api/v1/dashboard", "get", "/recent"),
        ("deeptutor.api.routers.plugins_api", "/api/v1/plugins", "get", "/list"),
        ("deeptutor.api.routers.tutorbot", "/api/v1/tutorbot", "get", ""),
    ],
)
def test_legacy_management_routes_require_admin(
    module_name: str,
    prefix: str,
    method: str,
    path: str,
) -> None:
    module = importlib.import_module(module_name)
    app = FastAPI()
    app.include_router(module.router, prefix=prefix)

    with TestClient(app) as client:
        response = getattr(client, method)(f"{prefix}{path}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
