"""HTTP endpoint for locally stored chat attachment previews."""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store
from deeptutor.services.storage import LocalDiskAttachmentStore, get_attachment_store
from deeptutor.tutorbot.utils.helpers import safe_filename

router = APIRouter()


def _content_disposition(filename: str, *, disposition: str = "inline") -> str:
    ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
    ascii_fallback = ascii_fallback.replace('"', "_").replace("\\", "_")
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _reject_path_filename(filename: str) -> None:
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise HTTPException(status_code=404, detail="Attachment not found")


async def _authorize_session_attachment_access(
    session_id: str,
    current_user: AuthContext,
) -> None:
    if session_id.startswith("feedback-"):
        if current_user.is_admin:
            return
        expected = f"feedback-{safe_filename(str(current_user.user_id or '').strip())}"
        if expected and session_id == expected:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    store = get_sqlite_session_store()
    owner_key = await store.get_session_owner_key(session_id)
    if owner_key:
        if current_user.is_admin or owner_key == build_user_owner_key(current_user.user_id):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    session = await store.get_session(session_id)
    if session is not None and current_user.is_admin:
        return
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/{session_id}/{attachment_id}/{filename:path}")
async def get_attachment(
    session_id: str,
    attachment_id: str,
    filename: str,
    current_user: AuthContext = Depends(get_current_user),
):
    _reject_path_filename(filename)
    await _authorize_session_attachment_access(session_id, current_user)

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
