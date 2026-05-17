from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.api.routers.attachments import router
from deeptutor.services.session import SQLiteSessionStore, build_user_owner_key
from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


def _build_app(
    monkeypatch,
    tmp_path: Path,
    *,
    current_user: AuthContext | None,
) -> tuple[TestClient, LocalDiskAttachmentStore, SQLiteSessionStore]:
    attachment_root = tmp_path / "attachments"
    session_db = tmp_path / "sessions.db"
    store = LocalDiskAttachmentStore(root=attachment_root)
    session_store = SQLiteSessionStore(db_path=session_db)

    monkeypatch.setattr(
        "deeptutor.api.routers.attachments.get_attachment_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "deeptutor.api.routers.attachments.get_sqlite_session_store",
        lambda: session_store,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/attachments")
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app), store, session_store


def _write_attachment(root: Path, session_id: str, name: str = "att-1_file.txt") -> None:
    session_dir = root / session_id
    session_dir.mkdir(parents=True)
    (session_dir / name).write_text("hello", encoding="utf-8")


def test_attachment_router_requires_authentication(monkeypatch, tmp_path: Path) -> None:
    client, store, session_store = _build_app(monkeypatch, tmp_path, current_user=None)
    asyncio.run(
        session_store.create_session(
            session_id="session-1",
            owner_key=build_user_owner_key("student_demo"),
        )
    )
    _write_attachment(store.root, "session-1")

    with client:
        response = client.get("/api/attachments/session-1/att-1/file.txt")

    assert response.status_code == 401


def test_attachment_router_serves_owner_file(monkeypatch, tmp_path: Path) -> None:
    client, store, session_store = _build_app(
        monkeypatch,
        tmp_path,
        current_user=_ctx("student_demo"),
    )
    asyncio.run(
        session_store.create_session(
            session_id="session-1",
            owner_key=build_user_owner_key("student_demo"),
        )
    )
    _write_attachment(store.root, "session-1")

    with client:
        response = client.get("/api/attachments/session-1/att-1/file.txt")

    assert response.status_code == 200
    assert response.text == "hello"
    assert response.headers["cache-control"] == "private, max-age=0, must-revalidate"


def test_attachment_router_rejects_non_owner(monkeypatch, tmp_path: Path) -> None:
    client, store, session_store = _build_app(
        monkeypatch,
        tmp_path,
        current_user=_ctx("student_demo"),
    )
    asyncio.run(
        session_store.create_session(
            session_id="session-1",
            owner_key=build_user_owner_key("student_other"),
        )
    )
    _write_attachment(store.root, "session-1")

    with client:
        response = client.get("/api/attachments/session-1/att-1/file.txt")

    assert response.status_code == 403


def test_attachment_router_allows_admin(monkeypatch, tmp_path: Path) -> None:
    client, store, session_store = _build_app(
        monkeypatch,
        tmp_path,
        current_user=_ctx("admin_demo", is_admin=True),
    )
    asyncio.run(
        session_store.create_session(
            session_id="session-1",
            owner_key=build_user_owner_key("student_other"),
        )
    )
    _write_attachment(store.root, "session-1")

    with client:
        response = client.get("/api/attachments/session-1/att-1/file.txt")

    assert response.status_code == 200
    assert response.text == "hello"


def test_attachment_router_rejects_path_traversal_even_when_basename_exists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client, store, session_store = _build_app(
        monkeypatch,
        tmp_path,
        current_user=_ctx("student_demo"),
    )
    asyncio.run(
        session_store.create_session(
            session_id="session-1",
            owner_key=build_user_owner_key("student_demo"),
        )
    )
    _write_attachment(store.root, "session-1")

    with client:
        response = client.get("/api/attachments/session-1/att-1/../file.txt")
        encoded = client.get("/api/attachments/session-1/att-1/%2E%2E/file.txt")

    assert response.status_code == 404
    assert encoded.status_code == 404
