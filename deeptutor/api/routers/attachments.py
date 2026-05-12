"""HTTP endpoint for locally stored chat attachment previews."""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from deeptutor.services.storage import LocalDiskAttachmentStore, get_attachment_store

router = APIRouter()


def _content_disposition(filename: str, *, disposition: str = "inline") -> str:
    ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
    ascii_fallback = ascii_fallback.replace('"', "_").replace("\\", "_")
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


@router.get("/{session_id}/{attachment_id}/{filename:path}")
async def get_attachment(session_id: str, attachment_id: str, filename: str):
    store = get_attachment_store()
    if not isinstance(store, LocalDiskAttachmentStore):
        raise HTTPException(status_code=501, detail="Attachment backend not servable")

    target = store.resolve_path(
        session_id=session_id,
        attachment_id=attachment_id,
        filename=filename,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    media_type, _ = mimetypes.guess_type(target.name)
    headers = {
        "Content-Disposition": _content_disposition(target.name),
        "Cache-Control": "private, max-age=0, must-revalidate",
    }
    return FileResponse(
        path=str(target),
        media_type=media_type or "application/octet-stream",
        headers=headers,
    )
