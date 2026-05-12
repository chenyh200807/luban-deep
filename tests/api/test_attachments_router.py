from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deeptutor.api.routers.attachments import router
from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore


def test_attachment_router_serves_only_store_resolved_files(monkeypatch, tmp_path: Path) -> None:
    store = LocalDiskAttachmentStore(root=tmp_path)
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    (session_dir / "att-1_file.txt").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(
        "deeptutor.api.routers.attachments.get_attachment_store",
        lambda: store,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/attachments")

    with TestClient(app) as client:
        response = client.get("/api/attachments/session-1/att-1/file.txt")
        missing = client.get("/api/attachments/session-1/att-1/../secret.txt")

    assert response.status_code == 200
    assert response.text == "hello"
    assert response.headers["cache-control"] == "private, max-age=0, must-revalidate"
    assert missing.status_code == 404
