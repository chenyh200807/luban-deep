from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore


@pytest.mark.asyncio
async def test_local_attachment_store_persists_with_safe_public_url(tmp_path: Path) -> None:
    store = LocalDiskAttachmentStore(root=tmp_path)

    url = await store.put(
        session_id="../session",
        attachment_id="att-1",
        filename="../资料.pdf",
        data=b"pdf-bytes",
        mime_type="application/pdf",
    )

    assert url.startswith("/api/attachments/session/att-1/")
    target = store.resolve_path(session_id="session", attachment_id="att-1", filename="资料.pdf")
    assert target is not None
    assert target.read_bytes() == b"pdf-bytes"
    assert target.resolve().is_relative_to(tmp_path.resolve())


def test_local_attachment_store_refuses_unknown_file(tmp_path: Path) -> None:
    store = LocalDiskAttachmentStore(root=tmp_path)

    assert store.resolve_path(
        session_id="session",
        attachment_id="att-1",
        filename="missing.pdf",
    ) is None
