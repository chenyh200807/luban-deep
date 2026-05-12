"""Persistent local storage for chat attachments."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote

from deeptutor.services.path_service import get_path_service
from deeptutor.tutorbot.utils.helpers import safe_filename

logger = logging.getLogger(__name__)

_ATTACHMENT_DIR_ENV = "CHAT_ATTACHMENT_DIR"
_DEFAULT_SUBPATH = ("workspace", "chat", "attachments")
_PUBLIC_URL_PREFIX = "/api/attachments"


def _coerce_filename(filename: str) -> str:
    base = os.path.basename(filename or "")
    cleaned = safe_filename(base)
    return cleaned or "file"


@runtime_checkable
class AttachmentStore(Protocol):
    async def put(
        self,
        *,
        session_id: str,
        attachment_id: str,
        filename: str,
        data: bytes,
        mime_type: str = "",
    ) -> str:
        """Persist bytes and return a relative public URL."""

    async def delete_session(self, session_id: str) -> None:
        """Best-effort cleanup of all attachments for a session."""

    def resolve_path(self, *, session_id: str, attachment_id: str, filename: str) -> Path | None:
        """Return an absolute path for a stored attachment, when locally servable."""


class LocalDiskAttachmentStore:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            override = os.environ.get(_ATTACHMENT_DIR_ENV, "").strip()
            if override:
                root = Path(override).expanduser().resolve()
            else:
                root = (get_path_service().get_user_root().joinpath(*_DEFAULT_SUBPATH)).resolve()
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def _stored_filename(self, attachment_id: str, filename: str) -> str:
        return f"{_coerce_filename(attachment_id)}_{_coerce_filename(filename)}"

    def _session_dir(self, session_id: str) -> Path:
        return (self._root / _coerce_filename(session_id)).resolve()

    def _safe_join(self, session_id: str, name: str) -> Path | None:
        candidate = (self._session_dir(session_id) / name).resolve()
        try:
            candidate.relative_to(self._root.resolve())
        except ValueError:
            return None
        return candidate

    async def put(
        self,
        *,
        session_id: str,
        attachment_id: str,
        filename: str,
        data: bytes,
        mime_type: str = "",
    ) -> str:
        del mime_type
        stored = self._stored_filename(attachment_id, filename)
        target = self._safe_join(session_id, stored)
        if target is None:
            raise ValueError(f"refusing to write attachment outside storage root: {stored!r}")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_sync, target, data)

        sid = quote(_coerce_filename(session_id), safe="")
        aid = quote(_coerce_filename(attachment_id), safe="")
        name = quote(_coerce_filename(filename), safe="")
        return f"{_PUBLIC_URL_PREFIX}/{sid}/{aid}/{name}"

    @staticmethod
    def _write_sync(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    async def delete_session(self, session_id: str) -> None:
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._rmtree_sync, session_dir)

    @staticmethod
    def _rmtree_sync(path: Path) -> None:
        import shutil

        try:
            shutil.rmtree(path)
        except OSError as exc:
            logger.warning("failed to clean up attachment dir %s: %s", path, exc)

    def resolve_path(self, *, session_id: str, attachment_id: str, filename: str) -> Path | None:
        stored = self._stored_filename(attachment_id, filename)
        target = self._safe_join(session_id, stored)
        if target is None or not target.is_file():
            return None
        return target


_stores: dict[str, AttachmentStore] = {}


def get_attachment_store() -> AttachmentStore:
    override = os.environ.get(_ATTACHMENT_DIR_ENV, "").strip()
    root = (
        Path(override).expanduser().resolve()
        if override
        else get_path_service().get_user_root().joinpath(*_DEFAULT_SUBPATH).resolve()
    )
    key = str(root)
    if key not in _stores:
        _stores[key] = LocalDiskAttachmentStore(root=root)
    return _stores[key]


def reset_attachment_store() -> None:
    _stores.clear()
