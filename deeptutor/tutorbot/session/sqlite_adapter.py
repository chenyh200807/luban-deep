"""SessionManager adapter backed by DeepTutor's SQLite store.

Implements the SessionManager interface (get_or_create, save, list_sessions) but
reads/writes through DeepTutor's SQLiteSessionStore, unifying conversation history
for TutorBot and DeepTutor in a single database.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from deeptutor.services.session.sqlite_store import build_user_owner_key
from deeptutor.tutorbot.session.manager import Session


class SQLiteSessionAdapter:
    """Drop-in replacement for SessionManager, backed by DeepTutor SQLite."""

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: A DeepTutor SQLiteSessionStore instance.
        """
        self.store = store
        self._cache: dict[str, Session] = {}

    @property
    def sessions_dir(self) -> Path:
        """Compatibility stub — not used when persisting to SQLite."""
        return Path("/dev/null")

    @property
    def workspace(self) -> Path:
        return Path("/dev/null")

    def _session_id(self, key: str) -> str:
        """Derive a stable DeepTutor session_id from a TutorBot key (channel:chat_id)."""
        return f"tutorbot:{key}"

    @staticmethod
    def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
        return dict(metadata or {})

    @staticmethod
    def _owner_key_from_metadata(metadata: dict[str, Any]) -> str:
        return build_user_owner_key(metadata.get("user_id"))

    @staticmethod
    def _source_from_metadata(metadata: dict[str, Any]) -> str | None:
        value = str(metadata.get("source") or "").strip().lower()
        return value or None

    @staticmethod
    def _title_from_metadata(key: str, metadata: dict[str, Any]) -> str:
        return str(metadata.get("title") or "").strip() or f"TutorBot: {key}"

    def get_or_create(self, key: str) -> Session:
        """Get or create a session synchronously (loads from SQLite via event loop)."""
        if key in self._cache:
            return self._cache[key]

        session = self._load_sync(key)
        if session is None:
            session = Session(key=key)
            self._ensure_sqlite_session_sync(key)
        self._cache[key] = session
        return session

    def save(self, session: Session) -> None:
        """Persist session messages to SQLite synchronously."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_async(session))
        except RuntimeError:
            asyncio.run(self._save_async(session))

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.store._list_sessions_sync(limit=50)

    def _load_sync(self, key: str) -> Session | None:
        """Load a session from SQLite by running the coroutine."""
        session_id = self._session_id(key)
        try:
            session_row = self.store._get_session_sync(session_id)
            messages_raw = self.store._get_messages_sync(session_id)
        except Exception:
            return None

        if session_row is None:
            return None

        messages: list[dict[str, Any]] = []
        for message in messages_raw:
            events = message.get("events") if isinstance(message.get("events"), list) else []
            raw_message = next(
                (
                    item.get("_tutorbot_message")
                    for item in events
                    if isinstance(item, dict) and isinstance(item.get("_tutorbot_message"), dict)
                ),
                None,
            )
            if isinstance(raw_message, dict):
                messages.append(dict(raw_message))
                continue
            messages.append(
                {
                    "role": message.get("role", "user"),
                    "content": message.get("content", ""),
                    "timestamp": message.get("created_at", ""),
                }
            )

        metadata = self._normalize_metadata(session_row.get("preferences"))
        metadata.setdefault("title", session_row.get("title") or "")
        metadata.setdefault("source", metadata.get("source") or "")
        return Session(
            key=key,
            messages=messages,
            created_at=datetime.fromtimestamp(float(session_row.get("created_at") or datetime.now().timestamp())),
            updated_at=datetime.fromtimestamp(float(session_row.get("updated_at") or datetime.now().timestamp())),
            metadata=metadata,
        )

    def _ensure_sqlite_session_sync(self, key: str, metadata: dict[str, Any] | None = None) -> None:
        """Ensure a corresponding DeepTutor session row exists."""
        session_id = self._session_id(key)
        normalized_metadata = self._normalize_metadata(metadata)
        coro = self.store.create_session(
            title=self._title_from_metadata(key, normalized_metadata),
            session_id=session_id,
            owner_key=self._owner_key_from_metadata(normalized_metadata) or None,
            source=self._source_from_metadata(normalized_metadata),
            archived=bool(normalized_metadata.get("archived", False)),
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        try:
            if loop and loop.is_running():
                loop.create_task(coro)
            elif loop:
                loop.run_until_complete(coro)
            else:
                asyncio.run(coro)
        except Exception:
            logger.debug("Session {} may already exist", session_id)

    async def _save_async(self, session: Session) -> None:
        """Write new messages to SQLite."""
        session_id = self._session_id(session.key)
        metadata = self._normalize_metadata(session.metadata)

        existing = await self.store.get_session(session_id)
        if existing is None:
            await self.store.create_session(
                title=self._title_from_metadata(session.key, metadata),
                session_id=session_id,
                owner_key=self._owner_key_from_metadata(metadata) or None,
                source=self._source_from_metadata(metadata),
                archived=bool(metadata.get("archived", False)),
            )
            if metadata:
                await self.store.update_session_preferences(session_id, metadata)
        else:
            title = self._title_from_metadata(session.key, metadata)
            if title and title != str(existing.get("title") or ""):
                await self.store.update_session_title(session_id, title)
            if metadata:
                await self.store.update_session_preferences(session_id, metadata)

        existing_msgs = await self.store.get_messages(session_id)
        existing_count = len(existing_msgs)

        for msg in session.messages[existing_count:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            await self.store.add_message(
                session_id=session_id,
                role=role,
                content=content,
                capability="tutorbot",
                events=[{"_tutorbot_message": dict(msg)}],
            )
        self._cache[session.key] = session
