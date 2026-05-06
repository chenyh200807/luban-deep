from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_local_attachment_store_persists_and_resolves_path(tmp_path) -> None:
    from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore

    store = LocalDiskAttachmentStore(root=tmp_path)
    url = await store.put(
        session_id="../session 1",
        attachment_id="att-1",
        filename="../hello world.txt",
        data=b"hello",
        mime_type="text/plain",
    )

    assert url == "/api/attachments/session%201/att-1/hello%20world.txt"
    path = store.resolve_path(
        session_id="../session 1",
        attachment_id="att-1",
        filename="../hello world.txt",
    )
    assert path is not None
    assert path.read_bytes() == b"hello"
    assert tmp_path.resolve() in path.resolve().parents

    await store.delete_session("../session 1")
    assert not path.exists()
