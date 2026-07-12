"""SessionManager adapter backed by DeepTutor's SQLite store.

Implements the SessionManager interface (get_or_create, save, list_sessions) but
reads/writes through DeepTutor's SQLiteSessionStore, unifying conversation history
for TutorBot and DeepTutor in a single database.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from loguru import logger

from deeptutor.runtime.safety import spawn_task
from deeptutor.tutorbot.session.manager import Session
from deeptutor.tutorbot.utils.helpers import normalize_message_content

# Engine-owned session rows always declare themselves as TutorBot-internal.
# "tutorbot" is the pre-existing engine source value (see
# deeptutor/services/tutorbot/manager.py send_message source fallback).
_ENGINE_SESSION_SOURCE = "tutorbot"

# In-memory LRU cap for hydrated sessions. The single persistence authority is
# SQLite; this cache and the persistence cursor below are process-local derived
# state — eviction (or process restart) simply forces a reload / full
# re-validation, so the cap prevents unbounded growth without adding a decider.
# Sized well above single-worker concurrency (~10) to keep it a safety bound,
# not a tuning knob.
_SESSION_CACHE_MAX = 1024


class SQLiteSessionAdapter:
    """Drop-in replacement for SessionManager, backed by DeepTutor SQLite."""

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: A DeepTutor SQLiteSessionStore instance.
        """
        self.store = store
        # OrderedDict = LRU: most-recently-used moved to the end, oldest evicted.
        self._cache: OrderedDict[str, Session] = OrderedDict()
        self._save_locks: dict[str, asyncio.Lock] = {}
        # Per-session persistence cursor: number of stable messages already
        # written to SQLite. Lets a hot save append only the new tail instead of
        # reading back the full history and re-signing every row. ``None`` (or a
        # missing key) means "not yet validated this process" → first save runs
        # the one-time full stability check.
        self._persisted_stable: dict[str, int] = {}

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
    def _metadata_for_persistence(metadata: dict[str, Any]) -> dict[str, Any]:
        """Single persistence gate: engine rows must never masquerade as user conversations.

        The bot-side mirror row (id ``tutorbot:<key>``) is TutorBot's private
        history store. The canonical conversation row (written by turn_runtime /
        REST createConversation) is the single user-facing session authority.
        Strip user identity and force the engine source before persisting, so
        every owner/identity/source-based reader (mobile conversation listing,
        BI registered-member scoping, member console activity) structurally
        never counts the mirror as a second user conversation. Root cause of
        the 2026-07 duplicate-session BI pollution: these rows used to carry
        ``owner_key=user:<uid>`` + ``source=wx_miniprogram``.

        Note: ``update_session_preferences`` re-derives the ``owner_key`` and
        ``source`` columns from the merged preferences JSON, so this must gate
        ALL create/update persistence calls in this adapter — fixing only
        ``create_session`` would be stomped by the next save.
        """
        normalized = dict(metadata or {})
        normalized.pop("user_id", None)
        normalized.pop("owner_key", None)
        normalized["source"] = _ENGINE_SESSION_SOURCE
        return normalized

    @staticmethod
    def _title_from_metadata(key: str, metadata: dict[str, Any]) -> str:
        return str(metadata.get("title") or "").strip() or f"TutorBot: {key}"

    @staticmethod
    def _message_signature(message: dict[str, Any]) -> tuple[Any, ...]:
        return (
            message.get("role", "user"),
            normalize_message_content(message.get("content")),
            json.dumps(message.get("tool_calls", []), ensure_ascii=False, sort_keys=True),
            message.get("tool_call_id", ""),
            message.get("name", ""),
        )

    @staticmethod
    def _message_for_sqlite(message: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(message)
        if normalized.get("role") == "user":
            raw_user_message = str(normalized.get("raw_user_message") or "").strip()
            if raw_user_message:
                normalized["content"] = raw_user_message
        normalized.pop("raw_user_message", None)
        return normalized

    @classmethod
    def _stored_tutorbot_messages(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for row in rows:
            events = row.get("events") if isinstance(row.get("events"), list) else []
            raw_message = next(
                (
                    item.get("_tutorbot_message")
                    for item in events
                    if isinstance(item, dict) and isinstance(item.get("_tutorbot_message"), dict)
                ),
                None,
            )
            if isinstance(raw_message, dict):
                normalized = dict(raw_message)
                normalized["content"] = normalize_message_content(normalized.get("content"))
                normalized.pop("reasoning_content", None)
                normalized.pop("thinking_blocks", None)
                messages.append(normalized)
                continue
            messages.append(
                {
                    "role": row.get("role", "user"),
                    "content": normalize_message_content(row.get("content")),
                    "timestamp": row.get("created_at", ""),
                }
            )
        return messages

    @classmethod
    def _stored_rows_are_stable(cls, rows: list[dict[str, Any]]) -> bool:
        stored_messages = cls._stored_tutorbot_messages(rows)
        stable_messages = Session(key="stable-check", messages=stored_messages).stable_messages()
        if len(stored_messages) != len(stable_messages):
            return False
        return all(
            cls._message_signature(left) == cls._message_signature(right)
            for left, right in zip(stored_messages, stable_messages, strict=False)
        )

    async def _rebuild_sqlite_session(
        self,
        *,
        session_id: str,
        session_key: str,
        metadata: dict[str, Any],
        stable_messages: list[dict[str, Any]],
    ) -> None:
        await self.store.delete_session(session_id)
        persist_metadata = self._metadata_for_persistence(metadata)
        await self.store.create_session(
            title=self._title_from_metadata(session_key, metadata),
            session_id=session_id,
            owner_key=None,
            source=_ENGINE_SESSION_SOURCE,
            archived=bool(metadata.get("archived", False)),
        )
        if persist_metadata:
            await self.store.update_session_preferences(session_id, persist_metadata)
        for msg in stable_messages:
            stored_message = self._message_for_sqlite(msg)
            await self.store.add_message(
                session_id=session_id,
                role=stored_message.get("role", "user"),
                content=stored_message.get("content", ""),
                capability="tutorbot",
                events=[{"_tutorbot_message": stored_message}],
            )

    async def get_or_create(self, key: str) -> Session:
        """Get or create a session, hydrating from SQLite via the store's async API.

        Single interface (no sync/async fork): callers await this from their own
        async context. The load path goes through the store's public async
        methods (``get_session`` / ``get_messages``), so it no longer reaches
        past the store's ``to_thread`` boundary into private ``*_sync`` methods.
        """
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        session = await self._load(key)
        if session is None:
            session = Session(key=key)
            await self._ensure_sqlite_session_async(key, {})
        self._cache[key] = session
        self._evict_if_over_limit()
        return session

    def save(self, session: Session) -> None:
        """Persist session messages to SQLite synchronously."""
        try:
            loop = asyncio.get_running_loop()
            spawn_task(
                self._save_async(session),
                name=f"tutorbot.sqlite.save:{session.key}",
            )
        except RuntimeError:
            asyncio.run(self._save_async(session))

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
        # Drop the persistence cursor too, so the next save re-validates from
        # SQLite — keeps cursor and cache lifetimes identical.
        self._persisted_stable.pop(self._session_id(key), None)

    def _evict_if_over_limit(self) -> None:
        """Evict least-recently-used sessions once the cache exceeds the cap.

        Skips any session whose save lock is currently held, so an in-flight
        writer never has its cursor dropped mid-append. Eviction mirrors
        ``invalidate``: both cache entry and cursor go, and the next
        ``get_or_create`` reloads from SQLite (the single authority).
        """
        while len(self._cache) > _SESSION_CACHE_MAX:
            victim: str | None = None
            for cached_key in self._cache:
                lock = self._save_locks.get(self._session_id(cached_key))
                if lock is not None and lock.locked():
                    continue
                victim = cached_key
                break
            if victim is None:
                # Every cached session is mid-save; leave the cap slightly
                # exceeded rather than evict a session being written.
                break
            self._cache.pop(victim, None)
            self._persisted_stable.pop(self._session_id(victim), None)

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.store._list_sessions_sync(limit=50)

    async def _load(self, key: str) -> Session | None:
        """Load a session from SQLite through the store's public async API."""
        session_id = self._session_id(key)
        try:
            session_row = await self.store.get_session(session_id)
            messages_raw = await self.store.get_messages(session_id)
        except Exception:
            logger.exception("Failed to load TutorBot SQLite session {}", session_id)
            raise

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
                normalized = dict(raw_message)
                normalized["content"] = normalize_message_content(normalized.get("content"))
                normalized.pop("reasoning_content", None)
                normalized.pop("thinking_blocks", None)
                messages.append(normalized)
                continue
            messages.append(
                {
                    "role": message.get("role", "user"),
                    "content": normalize_message_content(message.get("content")),
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

    async def _ensure_sqlite_session_async(self, key: str, metadata: dict[str, Any]) -> None:
        session_id = self._session_id(key)
        persist_metadata = self._metadata_for_persistence(metadata)
        lock = self._save_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            existing = await self.store.get_session(session_id)
            if existing is not None:
                if persist_metadata:
                    await self.store.update_session_preferences(session_id, persist_metadata)
                return
            await self.store.create_session(
                title=self._title_from_metadata(key, metadata),
                session_id=session_id,
                owner_key=None,
                source=_ENGINE_SESSION_SOURCE,
                archived=bool(metadata.get("archived", False)),
            )
            if persist_metadata:
                await self.store.update_session_preferences(session_id, persist_metadata)

    async def _save_async(self, session: Session) -> None:
        """Write new messages to SQLite."""
        session_id = self._session_id(session.key)
        metadata = self._normalize_metadata(session.metadata)
        lock = self._save_locks.setdefault(session_id, asyncio.Lock())

        async with lock:
            persist_metadata = self._metadata_for_persistence(metadata)
            existing = await self.store.get_session(session_id)
            if existing is None:
                await self.store.create_session(
                    title=self._title_from_metadata(session.key, metadata),
                    session_id=session_id,
                    owner_key=None,
                    source=_ENGINE_SESSION_SOURCE,
                    archived=bool(metadata.get("archived", False)),
                )
                if persist_metadata:
                    await self.store.update_session_preferences(session_id, persist_metadata)
            else:
                title = self._title_from_metadata(session.key, metadata)
                if title and title != str(existing.get("title") or ""):
                    await self.store.update_session_title(session_id, title)
                if persist_metadata:
                    await self.store.update_session_preferences(session_id, persist_metadata)

            stable_messages = session.stable_messages()
            # Persistence cursor: the adapter only ever writes stable messages
            # (one row per stable message), so the row count equals the number of
            # stable messages already persisted. A hot save appends just the new
            # tail. The full read-back + O(n) signature comparison is only needed
            # the FIRST time this process touches the session (cursor is None):
            # once the adapter owns the rows they stay stable-by-construction, so
            # later saves can trust the cursor. Losing the cursor (restart /
            # invalidate / LRU eviction) simply reruns the one-time check — same
            # end state, never a duplicate append.
            existing_count = self._persisted_stable.get(session_id)
            if existing_count is None:
                existing_msgs = await self.store.get_messages(session_id)
                if existing_msgs and not await asyncio.to_thread(
                    self._stored_rows_are_stable, existing_msgs
                ):
                    await self._rebuild_sqlite_session(
                        session_id=session_id,
                        session_key=session.key,
                        metadata=metadata,
                        stable_messages=stable_messages,
                    )
                    existing_count = len(stable_messages)
                else:
                    existing_count = len(existing_msgs)

            for msg in stable_messages[existing_count:]:
                stored_message = self._message_for_sqlite(msg)
                role = stored_message.get("role", "user")
                content = stored_message.get("content", "")
                await self.store.add_message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    capability="tutorbot",
                    events=[{"_tutorbot_message": stored_message}],
                )
            # Advance the cursor. ``max`` guards the degenerate case where a save
            # sees fewer stable messages than are already persisted (nothing was
            # appended above): never lower the watermark below what SQLite holds.
            self._persisted_stable[session_id] = max(existing_count, len(stable_messages))
        self._cache[session.key] = session
