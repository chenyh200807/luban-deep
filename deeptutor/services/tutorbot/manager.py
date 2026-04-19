"""
TutorBot Manager — spawn / stop / manage in-process TutorBot instances.

Each TutorBot instance runs as a set of asyncio tasks within the DeepTutor
server process.  Every bot gets its own isolated workspace under
``data/tutorbot/{bot_id}/`` containing workspace, cron, logs, and media.
Memory is shared across all bots via ``data/memory/``.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
import logging
import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from deeptutor.services.observability import get_langfuse_observability
from deeptutor.services.user_visible_output import coerce_user_visible_answer
from deeptutor.services.path_service import get_path_service
from deeptutor.services.session import build_user_owner_key, get_sqlite_session_store
from deeptutor.tutorbot.utils.helpers import safe_filename

logger = logging.getLogger(__name__)
observability = get_langfuse_observability()

_PACKAGE_TUTORBOT = Path(__file__).resolve().parent.parent.parent / "tutorbot"
_BUILTIN_SKILLS_DIR = _PACKAGE_TUTORBOT / "skills"
_BUILTIN_TEMPLATES_DIR = _PACKAGE_TUTORBOT / "templates"

_RESERVED_NAMES = {"workspace", "media", "cron", "logs", "sessions", "_souls"}


@dataclass
class BotConfig:
    """Configuration for a single TutorBot instance."""

    name: str
    description: str = ""
    persona: str = ""
    channels: dict[str, Any] = field(default_factory=dict)
    model: str | None = None


@dataclass
class TutorBotInstance:
    """A running TutorBot and its metadata."""

    bot_id: str
    config: BotConfig
    started_at: datetime = field(default_factory=datetime.now)
    tasks: list[asyncio.Task] = field(default_factory=list, repr=False)
    agent_loop: Any = None
    channel_manager: Any = None
    heartbeat: Any = None
    notify_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    channel_bindings: dict[str, str] = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return any(not t.done() for t in self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "name": self.config.name,
            "description": self.config.description,
            "persona": self.config.persona,
            "channels": list(self.config.channels.keys()),
            "model": self.config.model,
            "running": self.running,
            "started_at": self.started_at.isoformat(),
        }


class TutorBotManager:
    """Manage TutorBot instances running in-process."""

    def __init__(self) -> None:
        self._bots: dict[str, TutorBotInstance] = {}
        self._path_service = get_path_service()
        self._session_store = get_sqlite_session_store()

    # ── Path helpers ──────────────────────────────────────────────

    @property
    def _tutorbot_dir(self) -> Path:
        return self._path_service.project_root / "data" / "tutorbot"

    @property
    def _shared_memory_dir(self) -> Path:
        """Public memory shared by DeepTutor and all bots."""
        return self._path_service.get_memory_dir()

    def _bot_dir(self, bot_id: str) -> Path:
        return self._tutorbot_dir / bot_id

    def _bot_workspace(self, bot_id: str) -> Path:
        return self._bot_dir(bot_id) / "workspace"

    @staticmethod
    def build_chat_session_key(bot_id: str, chat_id: str, user_id: str | None = None) -> str:
        normalized_chat_id = str(chat_id or "web").strip() or "web"
        if user_id:
            normalized_user_id = str(user_id).strip()
            if normalized_user_id:
                return f"bot:{bot_id}:user:{normalized_user_id}:chat:{normalized_chat_id}"
        return f"bot:{bot_id}:chat:{normalized_chat_id}"

    @staticmethod
    def _infer_conversation_title(text: str) -> str:
        title = " ".join(str(text or "").strip().split())
        if not title:
            return "新对话"
        return title[:32] + ("..." if len(title) > 32 else "")

    def _session_path_for_key(self, bot_id: str, session_key: str) -> Path:
        safe_key = safe_filename(str(session_key or "").replace(":", "_"))
        return self._bot_workspace(bot_id) / "sessions" / f"{safe_key}.jsonl"

    @staticmethod
    def _sqlite_session_id_for_key(session_key: str) -> str:
        return f"tutorbot:{session_key}"

    def _sqlite_session_id_for_conversation(self, bot_id: str, conversation_id: str, *, user_id: str | None = None) -> str:
        session_key = self.build_chat_session_key(bot_id, conversation_id, user_id=user_id)
        return self._sqlite_session_id_for_key(session_key)

    @staticmethod
    def _row_matches_bot(row: dict[str, Any], bot_id: str) -> bool:
        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        pref_bot_id = str(preferences.get("bot_id") or "").strip()
        if pref_bot_id:
            return pref_bot_id == bot_id
        session_id = str(row.get("session_id") or row.get("id") or "").strip()
        return session_id.startswith(f"tutorbot:bot:{bot_id}:")

    @staticmethod
    def _conversation_id_from_row(row: dict[str, Any]) -> str:
        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        conversation_id = str(preferences.get("conversation_id") or "").strip()
        if conversation_id:
            return conversation_id
        session_id = str(row.get("session_id") or row.get("id") or "").strip()
        marker = ":chat:"
        if marker in session_id:
            return session_id.split(marker, 1)[1]
        return ""

    def _list_sqlite_bot_sessions(
        self,
        bot_id: str,
        *,
        owner_key: str | None = None,
        archived: bool | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if owner_key:
            rows = self._session_store._list_sessions_by_owner_sync(
                owner_key=owner_key,
                archived=archived,
                limit=max(limit * 3, 100),
            )
        else:
            rows = self._session_store._list_sessions_sync(limit=max(limit * 5, 200))
        filtered = [row for row in rows if self._row_matches_bot(row, bot_id)]
        filtered.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
        return filtered[:limit]

    def _load_session_file(self, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        import json as _json

        if not path.exists():
            return None
        try:
            metadata_line: dict[str, Any] = {}
            messages: list[dict[str, Any]] = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = _json.loads(line)
                    if data.get("_type") == "metadata":
                        metadata_line = data
                    else:
                        messages.append(data)
            return metadata_line, messages
        except Exception:
            logger.exception("Failed to load TutorBot session file: %s", path)
            return None

    def _rewrite_session_file(
        self,
        path: Path,
        metadata_line: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> None:
        import json as _json

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_json.dumps(metadata_line, ensure_ascii=False) + "\n")
            for msg in messages:
                f.write(_json.dumps(msg, ensure_ascii=False) + "\n")

    def list_bot_conversations(
        self,
        bot_id: str,
        *,
        user_id: str,
        archived: bool | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = self._list_sqlite_bot_sessions(
            bot_id,
            owner_key=build_user_owner_key(user_id),
            archived=archived,
            limit=limit,
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
            conversation_id = self._conversation_id_from_row(row)
            if not conversation_id:
                continue
            last_message = str(row.get("last_message") or "").strip()
            title = str(row.get("title") or "").strip() or self._infer_conversation_title(last_message)
            items.append(
                {
                    "id": conversation_id,
                    "title": title,
                    "last_message": last_message[:200],
                    "message_count": int(row.get("message_count") or 0),
                    "status": str(row.get("status") or "idle"),
                    "capability": str(row.get("capability") or "tutorbot"),
                    "source": str(preferences.get("source") or "wx_miniprogram"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "archived": bool(preferences.get("archived", False)),
                }
            )
        return items[:limit]

    def get_bot_conversation_messages(
        self,
        bot_id: str,
        *,
        user_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]] | None:
        session_id = self._sqlite_session_id_for_conversation(bot_id, conversation_id, user_id=user_id)
        row = self._session_store._get_session_sync(session_id)
        if row is None:
            return None
        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        if str(preferences.get("user_id") or "").strip() != str(user_id).strip():
            return None
        messages = self._session_store._get_messages_sync(session_id)

        result: list[dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role") or "").strip()
            if role not in {"user", "assistant"}:
                continue
            result.append(
                {
                    "role": role,
                    "content": msg.get("content", ""),
                    "created_at": msg.get("timestamp"),
                }
            )
        return result

    def update_bot_conversation_archive(
        self,
        bot_id: str,
        *,
        user_id: str,
        conversation_id: str,
        archived: bool,
    ) -> bool:
        session_id = self._sqlite_session_id_for_conversation(bot_id, conversation_id, user_id=user_id)
        row = self._session_store._get_session_sync(session_id)
        if row is None:
            return False
        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        if str(preferences.get("user_id") or "").strip() != str(user_id).strip():
            return False
        return self._session_store._update_session_preferences_sync(session_id, {"archived": bool(archived)})

    def delete_bot_conversation(
        self,
        bot_id: str,
        *,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        session_id = self._sqlite_session_id_for_conversation(bot_id, conversation_id, user_id=user_id)
        row = self._session_store._get_session_sync(session_id)
        if row is None:
            return False
        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        if str(preferences.get("user_id") or "").strip() != str(user_id).strip():
            return False
        return self._session_store._delete_session_sync(session_id)

    # ── Per-bot directory setup ───────────────────────────────────

    def _ensure_bot_dirs(self, bot_id: str) -> None:
        """Create the per-bot directory tree and seed skills/templates."""
        self._maybe_migrate_legacy(bot_id)

        for sub in ("workspace/skills", "workspace/memory", "cron", "logs", "media"):
            (self._bot_dir(bot_id) / sub).mkdir(parents=True, exist_ok=True)

        self._seed_skills(bot_id)
        self._seed_templates(bot_id)

    def _seed_skills(self, bot_id: str) -> None:
        """Copy built-in skill templates into the bot's workspace if absent."""
        if not _BUILTIN_SKILLS_DIR.exists():
            logger.warning("Builtin skills dir not found: %s", _BUILTIN_SKILLS_DIR)
            return
        dst = self._bot_workspace(bot_id) / "skills"
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for skill_dir in _BUILTIN_SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            target = dst / skill_dir.name
            if not target.exists():
                try:
                    shutil.copytree(skill_dir, target)
                    copied += 1
                except Exception:
                    logger.exception("Failed to copy skill '%s' for bot '%s'", skill_dir.name, bot_id)
        if copied:
            logger.info("Seeded %d skills for bot '%s' from %s", copied, bot_id, _BUILTIN_SKILLS_DIR)

    def _seed_templates(self, bot_id: str) -> None:
        """Copy per-bot template files into the bot's workspace if absent."""
        if not _BUILTIN_TEMPLATES_DIR.exists():
            return
        ws = self._bot_workspace(bot_id)
        for tpl in ("SOUL.md", "TOOLS.md", "USER.md", "HEARTBEAT.md", "AGENTS.md"):
            src = _BUILTIN_TEMPLATES_DIR / tpl
            dst = ws / tpl
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

    # ── Legacy data migration ─────────────────────────────────────

    def _maybe_migrate_legacy(self, bot_id: str) -> None:
        """Migrate from the old bots/ sub-directory layout.

        Old layout:
          data/tutorbot/bots/{bot_id}/config.yaml
          data/tutorbot/bots/{bot_id}/workspace/
          data/tutorbot/bots/{bot_id}/memory/

        New layout:
          data/tutorbot/{bot_id}/config.yaml
          data/tutorbot/{bot_id}/workspace/
          data/memory/   (shared)
        """
        new_config = self._bot_dir(bot_id) / "config.yaml"
        if new_config.exists():
            return

        legacy_bots = self._tutorbot_dir / "bots"

        # Migrate from bots/{id}/ to {id}/
        legacy_bot_dir = legacy_bots / bot_id
        if legacy_bot_dir.is_dir() and (legacy_bot_dir / "config.yaml").exists():
            target = self._bot_dir(bot_id)
            target.mkdir(parents=True, exist_ok=True)
            for item in legacy_bot_dir.iterdir():
                if item.name == "memory":
                    continue
                dest = target / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            logger.info("Migrated bot '%s' from bots/ sub-directory", bot_id)

        # Migrate legacy bots/{id}.yaml
        legacy_yaml = legacy_bots / f"{bot_id}.yaml"
        if legacy_yaml.is_file() and not new_config.exists():
            self._bot_dir(bot_id).mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_yaml), str(new_config))
            logger.info("Migrated bot config %s.yaml", bot_id)

    # ── Config persistence ────────────────────────────────────────

    def _load_bot_config(self, bot_id: str) -> BotConfig | None:
        path = self._bot_dir(bot_id) / "config.yaml"
        if not path.exists():
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return BotConfig(
                name=data.get("name", bot_id),
                description=data.get("description", ""),
                persona=data.get("persona", ""),
                channels=data.get("channels", {}),
                model=data.get("model"),
            )
        except Exception:
            logger.exception("Failed to load bot config %s", bot_id)
            return None

    def _save_bot_config(self, bot_id: str, config: BotConfig, *, auto_start: bool = True) -> None:
        bot_dir = self._bot_dir(bot_id)
        bot_dir.mkdir(parents=True, exist_ok=True)
        path = bot_dir / "config.yaml"
        data: dict[str, Any] = {
            "name": config.name,
            "description": config.description,
            "persona": config.persona,
            "channels": config.channels,
            "auto_start": auto_start,
        }
        if config.model:
            data["model"] = config.model
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    def _default_bot_config(self, bot_id: str) -> BotConfig:
        soul = self.get_soul(bot_id)
        if soul:
            return BotConfig(
                name=str(soul.get("name") or bot_id),
                persona=str(soul.get("content") or ""),
            )
        return BotConfig(name=bot_id)

    # ── Bot lifecycle ─────────────────────────────────────────────

    async def start_bot(self, bot_id: str, config: BotConfig | None = None) -> TutorBotInstance:
        """Start a TutorBot instance with its own isolated workspace."""
        if bot_id in self._bots and self._bots[bot_id].running:
            return self._bots[bot_id]

        self._ensure_bot_dirs(bot_id)

        if config is None:
            config = self._load_bot_config(bot_id)
        if config is None:
            config = self._default_bot_config(bot_id)
            self._save_bot_config(bot_id, config)

        from deeptutor.tutorbot.providers.deeptutor_adapter import create_deeptutor_provider
        from deeptutor.tutorbot.bus.queue import MessageBus
        from deeptutor.tutorbot.agent.loop import AgentLoop
        from deeptutor.tutorbot.config.schema import ExecToolConfig
        from deeptutor.tutorbot.session.sqlite_adapter import SQLiteSessionAdapter

        provider = create_deeptutor_provider()
        bus = MessageBus()

        workspace = self._bot_workspace(bot_id)
        session_adapter = SQLiteSessionAdapter(self._session_store)

        if config.persona:
            soul_path = workspace / "SOUL.md"
            soul_path.write_text(config.persona, encoding="utf-8")

        venv_bin = str(Path(sys.executable).parent)
        exec_config = ExecToolConfig(timeout=300, path_append=venv_bin)

        canonical_key = f"bot:{bot_id}"

        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            model=config.model,
            exec_config=exec_config,
            session_manager=session_adapter,
            shared_memory_dir=None,
            restrict_to_workspace=False,
            default_session_key=canonical_key,
        )

        # -- Channel setup ---------------------------------------------------
        channel_manager = None
        if config.channels:
            try:
                from deeptutor.tutorbot.channels.manager import ChannelManager
                from deeptutor.tutorbot.config.schema import ChannelsConfig

                channels_config = ChannelsConfig(**config.channels)
                channel_manager = ChannelManager(channels_config, bus)
                if channel_manager.channels:
                    logger.info(
                        "Channels enabled for bot '%s': %s",
                        bot_id, list(channel_manager.channels.keys()),
                    )
                else:
                    logger.info("No channels matched config for bot '%s'", bot_id)
                    channel_manager = None
            except Exception:
                logger.exception("Failed to initialise channels for bot '%s'", bot_id)
                channel_manager = None

        instance = TutorBotInstance(
            bot_id=bot_id,
            config=config,
            agent_loop=agent_loop,
            channel_manager=channel_manager,
        )

        # -- Core tasks -------------------------------------------------------
        loop_task = asyncio.create_task(
            agent_loop.run(), name=f"tutorbot:{bot_id}:loop",
        )
        router_task = asyncio.create_task(
            self._outbound_router(bot_id, bus, instance),
            name=f"tutorbot:{bot_id}:router",
        )
        instance.tasks.extend([loop_task, router_task])

        # -- Start channel listeners (without ChannelManager's own dispatcher)
        if channel_manager:
            for ch_name, ch in channel_manager.channels.items():
                ch_task = asyncio.create_task(
                    ch.start(), name=f"tutorbot:{bot_id}:ch:{ch_name}",
                )
                instance.tasks.append(ch_task)

        # -- Heartbeat --------------------------------------------------------
        from deeptutor.tutorbot.heartbeat import HeartbeatService

        async def _hb_execute(tasks_summary: str) -> str:
            return await agent_loop.process_direct(
                tasks_summary, session_key=canonical_key,
                channel="web", chat_id="web",
            )

        async def _hb_notify(response: str) -> None:
            await instance.notify_queue.put(response)

        heartbeat = HeartbeatService(
            workspace=workspace,
            provider=provider,
            model=agent_loop.model,
            on_execute=_hb_execute,
            on_notify=_hb_notify,
            interval_s=30 * 60,
        )
        instance.heartbeat = heartbeat
        await heartbeat.start()

        self._bots[bot_id] = instance
        self._save_bot_config(bot_id, config)
        logger.info("TutorBot '%s' started (workspace=%s)", bot_id, workspace)
        return instance

    async def ensure_bot_running(
        self,
        bot_id: str,
        config: BotConfig | None = None,
    ) -> TutorBotInstance:
        instance = self.get_bot(bot_id)
        if instance and instance.running:
            return instance
        return await self.start_bot(bot_id, config=config)

    async def _outbound_router(self, bot_id: str, bus: Any, instance: TutorBotInstance) -> None:
        """Route outbound messages to channels, web notify_queue, and EventBus.

        This is the sole consumer of the outbound queue, replacing both the
        old ``_bridge_events`` and ``ChannelManager._dispatch_outbound`` to
        avoid queue contention.
        """
        try:
            from deeptutor.events.event_bus import Event, EventType, get_event_bus
            from deeptutor.tutorbot.bus.events import OutboundMessage as _OMsg

            event_bus = get_event_bus()
            while True:
                msg: _OMsg = await bus.consume_outbound()
                is_progress = bool(msg.metadata and msg.metadata.get("_progress"))

                # 1. Route to originating channel (if it exists)
                if instance.channel_manager:
                    channel = instance.channel_manager.get_channel(msg.channel)
                    if channel:
                        try:
                            await channel.send(msg)
                        except Exception:
                            logger.exception("Failed to send to channel %s for bot %s", msg.channel, bot_id)
                        if not is_progress and msg.chat_id:
                            instance.channel_bindings[msg.channel] = msg.chat_id

                # 2. Notify web clients (non-progress only)
                if not is_progress:
                    await instance.notify_queue.put(msg.content or "")

                # 3. Publish to EventBus
                if not is_progress:
                    await event_bus.publish(Event(
                        type=EventType.CAPABILITY_COMPLETE,
                        task_id=f"tutorbot:{bot_id}:{msg.channel}:{msg.chat_id}",
                        user_input="",
                        agent_output=msg.content or "",
                        metadata={
                            "source": "tutorbot",
                            "bot_id": bot_id,
                            "channel": msg.channel,
                            "chat_id": msg.chat_id,
                        },
                    ))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Outbound router failed for bot %s", bot_id)

    async def stop_bot(self, bot_id: str) -> bool:
        """Stop a running TutorBot instance."""
        instance = self._bots.get(bot_id)
        if not instance:
            return False

        for task in instance.tasks:
            if not task.done():
                task.cancel()
        for task in instance.tasks:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if instance.channel_manager:
            try:
                await instance.channel_manager.stop_all()
            except Exception:
                logger.exception("Error stopping channels for bot '%s'", bot_id)

        if instance.heartbeat:
            instance.heartbeat.stop()

        if instance.agent_loop:
            try:
                await instance.agent_loop.stop()
            except Exception:
                pass

        self._save_bot_config(bot_id, instance.config, auto_start=False)
        del self._bots[bot_id]
        logger.info("TutorBot '%s' stopped", bot_id)
        return True

    # ── Listing & discovery ───────────────────────────────────────

    def _discover_bot_ids(self) -> set[str]:
        """Return all bot IDs found on disk."""
        ids: set[str] = set()
        if not self._tutorbot_dir.exists():
            return ids

        for entry in self._tutorbot_dir.iterdir():
            if entry.name in _RESERVED_NAMES:
                continue
            if entry.is_dir() and (entry / "config.yaml").exists():
                ids.add(entry.name)
        return ids

    def list_bots(self) -> list[dict[str, Any]]:
        """List all known bots (running + configured on disk)."""
        result: dict[str, dict[str, Any]] = {}

        for inst in self._bots.values():
            result[inst.bot_id] = inst.to_dict()

        for bid in self._discover_bot_ids():
            if bid in result:
                continue
            self._maybe_migrate_legacy(bid)
            cfg = self._load_bot_config(bid)
            result[bid] = {
                "bot_id": bid,
                "name": cfg.name if cfg else bid,
                "description": cfg.description if cfg else "",
                "persona": cfg.persona if cfg else "",
                "channels": list(cfg.channels.keys()) if cfg else [],
                "model": cfg.model if cfg else None,
                "running": False,
                "started_at": None,
            }

        return list(result.values())

    def get_bot(self, bot_id: str) -> TutorBotInstance | None:
        return self._bots.get(bot_id)

    def get_bot_history(self, bot_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Read chat messages from a bot's unified SQLite-backed sessions."""
        all_messages: list[dict[str, Any]] = []
        for row in self._list_sqlite_bot_sessions(bot_id, limit=max(limit * 3, 100)):
            session_id = str(row.get("session_id") or row.get("id") or "").strip()
            if not session_id:
                continue
            try:
                messages = self._session_store._get_messages_sync(session_id)
            except Exception:
                continue
            for msg in messages:
                if msg.get("role") in ("user", "assistant") and msg.get("content"):
                    all_messages.append(msg)
            if len(all_messages) >= limit:
                break
        return all_messages[-limit:]

    def get_recent_active_bots(self, limit: int = 3) -> list[dict[str, Any]]:
        """Return the most recently active bots with their last message preview."""
        bot_activity: list[tuple[float, str, dict[str, Any]]] = []

        for bid in self._discover_bot_ids():
            rows = self._list_sqlite_bot_sessions(bid, limit=1)
            if not rows:
                continue
            newest = rows[0]
            mtime = float(newest.get("updated_at") or 0.0)
            last_msg = str(newest.get("last_message") or "").strip()

            cfg = self._load_bot_config(bid)
            instance = self._bots.get(bid)
            bot_activity.append((mtime, bid, {
                "bot_id": bid,
                "name": cfg.name if cfg else bid,
                "running": instance.running if instance else False,
                "last_message": last_msg[:200] if last_msg else "",
                "updated_at": datetime.fromtimestamp(mtime).isoformat() if mtime else "",
            }))

        bot_activity.sort(key=lambda x: x[0], reverse=True)
        return [item[2] for item in bot_activity[:limit]]

    async def send_message(
        self,
        bot_id: str,
        content: str,
        chat_id: str = "web",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
        mode: str = "smart",
        session_key: str | None = None,
        session_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Send a message to a running bot and return the response."""
        instance = self._bots.get(bot_id)
        if not instance or not instance.running:
            raise RuntimeError(f"Bot '{bot_id}' is not running")

        effective_chat_id = str(chat_id or "web").strip() or "web"
        effective_session_key = session_key or self.build_chat_session_key(bot_id, effective_chat_id)

        session = instance.agent_loop.sessions.get_or_create(effective_session_key)
        merged_metadata = dict(session.metadata or {})
        if session_metadata:
            merged_metadata.update(session_metadata)
        merged_metadata.setdefault("conversation_id", effective_chat_id)
        if not merged_metadata.get("title"):
            merged_metadata["title"] = self._infer_conversation_title(content)
        session.metadata = merged_metadata
        instance.agent_loop.sessions.save(session)
        user_id = str(merged_metadata.get("user_id") or "").strip()
        source = str(merged_metadata.get("source") or "tutorbot").strip() or "tutorbot"
        external_session_id = str(merged_metadata.get("session_id") or "").strip()
        external_turn_id = str(merged_metadata.get("turn_id") or "").strip()
        trace_name = str(merged_metadata.get("trace_name") or "").strip() or f"tutorbot.{bot_id}"
        trace_session_id = external_session_id or effective_session_key
        turn_id = external_turn_id or f"{effective_session_key}:{datetime.now().timestamp()}"
        tool_trace_summary: dict[str, Any] = {
            "tool_calls": [],
            "sources": [],
            "authority_applied": False,
            "exact_question": {},
            "rag_rounds": [],
            "rag_saturation": {},
        }
        trace_metadata = {
            "trace_name": trace_name,
            "session_id": trace_session_id,
            "turn_id": turn_id,
            "user_id": user_id,
            "bot_id": bot_id,
            "execution_engine": "tutorbot_runtime",
            "conversation_id": effective_chat_id,
            "channel": "web",
            "capability": "tutorbot",
            "teaching_mode": mode,
            "requested_response_mode": str(merged_metadata.get("requested_response_mode") or mode).strip()
            or mode,
            "effective_response_mode": str(merged_metadata.get("effective_response_mode") or mode).strip()
            or mode,
            "response_mode_degrade_reason": str(
                merged_metadata.get("response_mode_degrade_reason") or ""
            ).strip(),
            "source": source,
            "title": str(merged_metadata.get("title") or "").strip(),
            "tutorbot_session_key": effective_session_key,
            "default_tools": list(merged_metadata.get("default_tools") or []),
            "knowledge_bases": list(merged_metadata.get("knowledge_bases") or []),
            "default_kb": str(merged_metadata.get("default_kb") or "").strip(),
        }

        async def _progress(text: str, *, tool_hint: bool = False) -> None:
            if on_progress:
                await on_progress(text)

        async def _tool_call(tool_name: str, args: dict[str, Any]) -> None:
            tool_trace_summary["tool_calls"].append(
                {
                    "name": str(tool_name or "").strip(),
                    "args": dict(args or {}),
                }
            )
            if on_tool_call:
                await on_tool_call(tool_name, args)

        async def _tool_result(
            tool_name: str,
            result: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            metadata = dict(metadata or {})
            sources = metadata.get("sources")
            if isinstance(sources, list) and sources:
                tool_trace_summary["sources"] = sources[:8]
            rag_rounds = metadata.get("rag_rounds")
            if isinstance(rag_rounds, list) and rag_rounds:
                tool_trace_summary["rag_rounds"] = [
                    dict(item) for item in rag_rounds if isinstance(item, dict)
                ]
            rag_saturation = metadata.get("rag_saturation")
            if isinstance(rag_saturation, dict) and rag_saturation:
                tool_trace_summary["rag_saturation"] = dict(rag_saturation)
            exact_question = metadata.get("exact_question")
            if isinstance(exact_question, dict) and exact_question:
                tool_trace_summary["exact_question"] = exact_question
                tool_trace_summary["authority_applied"] = bool(metadata.get("authority_applied", False))
            if on_tool_result:
                await on_tool_result(tool_name, result, metadata)

        runtime_metadata = dict(merged_metadata)
        runtime_metadata["teaching_mode"] = mode
        runtime_metadata["effective_response_mode"] = (
            str(merged_metadata.get("effective_response_mode") or mode).strip() or mode
        )

        response = ""
        try:
            with ExitStack() as stack:
                if not external_turn_id:
                    stack.enter_context(
                        observability.usage_scope(
                            scope_id=turn_id,
                            session_id=trace_session_id,
                            turn_id=turn_id,
                            capability="tutorbot",
                        )
                    )
                turn_observation = stack.enter_context(
                    observability.start_observation(
                        name="tutorbot.runtime" if external_turn_id else "turn.tutorbot",
                        as_type="chain",
                        input_payload={"content": content},
                        metadata=trace_metadata,
                    )
                )
                try:
                    response = await instance.agent_loop.process_direct(
                        content,
                        session_key=effective_session_key,
                        channel="web",
                        chat_id=effective_chat_id,
                        on_progress=_progress,
                        on_content_delta=on_content_delta,
                        on_tool_call=_tool_call,
                        on_tool_result=_tool_result,
                        metadata=runtime_metadata,
                    )
                    response = coerce_user_visible_answer(response)
                    usage_summary = observability.get_current_usage_summary()
                    observability.update_observation(
                        turn_observation,
                        output_payload={"assistant_content": response},
                        metadata={
                            **observability.summary_metadata(usage_summary),
                            **trace_metadata,
                            "tool_calls": tool_trace_summary["tool_calls"],
                            "actual_tool_rounds": len(tool_trace_summary["tool_calls"]),
                            "sources": tool_trace_summary["sources"],
                            "rag_rounds": tool_trace_summary["rag_rounds"],
                            "rag_round_count": len(tool_trace_summary["rag_rounds"]),
                            "rag_saturation": tool_trace_summary["rag_saturation"],
                            "authority_applied": tool_trace_summary["authority_applied"],
                            "exact_question": tool_trace_summary["exact_question"],
                        },
                        usage_details=observability.usage_details_from_summary(usage_summary),
                        cost_details=observability.cost_details_from_summary(usage_summary),
                        usage_source="summary",
                    )
                except asyncio.CancelledError:
                    usage_summary = observability.get_current_usage_summary()
                    observability.update_observation(
                        turn_observation,
                        output_payload={"assistant_content": response},
                        metadata={
                            **observability.summary_metadata(usage_summary),
                            **trace_metadata,
                        },
                        usage_details=observability.usage_details_from_summary(usage_summary),
                        cost_details=observability.cost_details_from_summary(usage_summary),
                        usage_source="summary",
                        level="ERROR",
                        status_message="TutorBot turn cancelled",
                    )
                    raise
                except Exception as exc:
                    usage_summary = observability.get_current_usage_summary()
                    observability.update_observation(
                        turn_observation,
                        output_payload={"assistant_content": response},
                        metadata={
                            **observability.summary_metadata(usage_summary),
                            **trace_metadata,
                        },
                        usage_details=observability.usage_details_from_summary(usage_summary),
                        cost_details=observability.cost_details_from_summary(usage_summary),
                        usage_source="summary",
                        level="ERROR",
                        status_message=str(exc),
                    )
                    raise
        finally:
            observability.flush()

        # Forward the reply to any bound external channels so mobile users
        # see the web-originated conversation in their chat app.
        if instance.channel_manager and response:
            from deeptutor.tutorbot.bus.events import OutboundMessage

            for ch_name, ch_chat_id in instance.channel_bindings.items():
                ch = instance.channel_manager.get_channel(ch_name)
                if ch:
                    try:
                        await ch.send(OutboundMessage(
                            channel=ch_name, chat_id=ch_chat_id, content=response,
                        ))
                    except Exception:
                        logger.exception(
                            "Failed to forward web reply to channel %s for bot %s",
                            ch_name, bot_id,
                        )

        return response

    async def auto_start_bots(self) -> None:
        """Scan persisted configs and start bots marked with auto_start: true."""
        for bid in self._discover_bot_ids():
            if bid in self._bots and self._bots[bid].running:
                continue
            try:
                self._maybe_migrate_legacy(bid)
                path = self._bot_dir(bid) / "config.yaml"
                if not path.exists():
                    continue
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if not data.get("auto_start", False):
                    continue
                config = BotConfig(
                    name=data.get("name", bid),
                    description=data.get("description", ""),
                    persona=data.get("persona", ""),
                    channels=data.get("channels", {}),
                    model=data.get("model"),
                )
                await self.start_bot(bid, config)
                logger.info("Auto-started bot '%s'", bid)
            except Exception:
                logger.exception("Failed to auto-start bot '%s'", bid)

    async def destroy_bot(self, bot_id: str) -> bool:
        """Stop a bot (if running) and permanently delete its data from disk."""
        await self.stop_bot(bot_id)
        bot_dir = self._bot_dir(bot_id)
        if not bot_dir.exists():
            return False
        shutil.rmtree(bot_dir)
        logger.info("TutorBot '%s' destroyed (data deleted)", bot_id)
        return True

    # ── Workspace file helpers ────────────────────────────────────

    _EDITABLE_FILES = {"SOUL.md", "USER.md", "TOOLS.md", "AGENTS.md", "HEARTBEAT.md"}

    def read_bot_file(self, bot_id: str, filename: str) -> str | None:
        if filename not in self._EDITABLE_FILES:
            return None
        path = self._bot_workspace(bot_id) / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_bot_file(self, bot_id: str, filename: str, content: str) -> bool:
        if filename not in self._EDITABLE_FILES:
            return False
        path = self._bot_workspace(bot_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True

    def read_all_bot_files(self, bot_id: str) -> dict[str, str]:
        result: dict[str, str] = {}
        ws = self._bot_workspace(bot_id)
        for fn in self._EDITABLE_FILES:
            path = ws / fn
            result[fn] = path.read_text(encoding="utf-8") if path.exists() else ""
        return result

    async def stop_all(self) -> None:
        """Stop all running bots."""
        for bot_id in list(self._bots.keys()):
            await self.stop_bot(bot_id)

    # ── Soul template library ─────────────────────────────────────

    @property
    def _souls_file(self) -> Path:
        return self._tutorbot_dir / "_souls.yaml"

    def _load_souls(self) -> list[dict[str, str]]:
        path = self._souls_file
        if not path.exists():
            self._seed_default_souls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            souls = data if isinstance(data, list) else []
            return self._merge_default_souls(souls)
        except Exception:
            return self._default_souls()

    def _save_souls(self, souls: list[dict[str, str]]) -> None:
        self._tutorbot_dir.mkdir(parents=True, exist_ok=True)
        self._souls_file.write_text(
            yaml.dump(souls, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    @staticmethod
    def _default_souls() -> list[dict[str, str]]:
        return [
            {"id": "default-tutorbot", "name": "Default TutorBot", "content": (
                "# Soul\n\nI am TutorBot, a personal learning companion.\n\n"
                "## Personality\n\n- Helpful and friendly\n- Clear, encouraging, and patient\n"
                "- Adapts explanations to the user's level\n\n"
                "## Values\n\n- Accuracy over speed\n- User privacy and safety\n- Transparency in actions"
            )},
            {"id": "math-tutor", "name": "Math Tutor", "content": (
                "# Soul\n\nI am a math tutor specializing in clear, step-by-step problem solving.\n\n"
                "## Personality\n\n- Patient and methodical\n- Encourages showing work\n"
                "- Celebrates progress on hard problems\n\n"
                "## Teaching Style\n\n- Break complex problems into small steps\n"
                "- Use visual representations when possible\n- Always verify final answers"
            )},
            {"id": "coding-assistant", "name": "Coding Assistant", "content": (
                "# Soul\n\nI am a coding assistant focused on helping developers write better software.\n\n"
                "## Personality\n\n- Precise and detail-oriented\n"
                "- Pragmatic — working code over perfect code\n- Explains trade-offs clearly\n\n"
                "## Approach\n\n- Read before writing; understand context first\n"
                "- Suggest tests alongside implementations\n- Prefer standard patterns over clever tricks"
            )},
            {"id": "research-helper", "name": "Research Helper", "content": (
                "# Soul\n\nI am a research assistant helping users explore academic topics in depth.\n\n"
                "## Personality\n\n- Curious and thorough\n"
                "- Balanced — presents multiple perspectives\n- Cites sources when possible\n\n"
                "## Approach\n\n- Decompose broad questions into focused sub-questions\n"
                "- Distinguish established facts from open questions\n- Suggest further reading"
            )},
            {"id": "language-tutor", "name": "Language Tutor", "content": (
                "# Soul\n\nI am a language learning companion helping users practice and improve.\n\n"
                "## Personality\n\n- Encouraging and patient\n"
                "- Adapts difficulty to learner level\n- Makes learning fun with examples\n\n"
                "## Teaching Style\n\n- Correct mistakes gently with explanations\n"
                "- Use contextual examples over abstract rules\n- Encourage speaking/writing practice"
            )},
            {"id": "construction-exam-coach", "name": "Construction Exam Coach", "content": (
                "# Soul\n\n"
                "你是鲁班智考中的建筑实务备考导师，保持专业教师风格，但不要自称具体真人姓名。\n\n"
                "## 角色定位\n\n"
                "- 你的首要目标是帮助学员把题做对、把分拿稳、把同类题学会\n"
                "- 你不是泛泛答疑助手，而是长期陪学型建筑实务导师\n"
                "- 你默认服务考试备考场景，回答优先从应试、拿分、避坑、迁移角度组织\n\n"
                "## 核心原则\n\n"
                "- 结论先行：先给答案、判断或结论，再解释原因\n"
                "- 面向拿分：讲知识时落到考点、判定依据、踩分点、易错点\n"
                "- 说人话：用通俗语言解释规范逻辑，不堆空泛定义\n"
                "- 先帮学员拿到这题，再帮学员学会这类题\n"
                "- 案例题、实务题优先给作答骨架，再补教学说明\n\n"
                "## 专业约束\n\n"
                "- 遇到规范数值、程序门槛、时间节点等具体事实，优先依赖知识库和检索证据\n"
                "- 证据不足时，不编造规范编号，不伪造精确条文，不捏造参数\n"
                "- 可以给通用判断逻辑，但不要把经验说成已核实事实\n\n"
                "## 默认表达风格\n\n"
                "- 专业、直接、稳，像经验丰富的建筑实务老师\n"
                "- 结构化、简洁、口语化，但保持专业度\n"
                "- 默认用陈述句收尾，不强行追问\n"
                "- 学员焦虑或挫败时，先稳定情绪，再缩小问题、降低复杂度"
            )},
        ]

    def _seed_default_souls(self) -> None:
        defaults = self._default_souls()
        self._save_souls(defaults)

    def _merge_default_souls(self, souls: list[dict[str, str]]) -> list[dict[str, str]]:
        merged = list(souls)
        existing_ids = {str(item.get("id", "")).strip() for item in souls}
        changed = False
        for soul in self._default_souls():
            if soul["id"] in existing_ids:
                continue
            merged.append(soul)
            changed = True
        if changed:
            self._save_souls(merged)
        return merged

    def list_souls(self) -> list[dict[str, str]]:
        return self._load_souls()

    def get_soul(self, soul_id: str) -> dict[str, str] | None:
        for s in self._load_souls():
            if s.get("id") == soul_id:
                return s
        return None

    def create_soul(self, soul_id: str, name: str, content: str) -> dict[str, str]:
        souls = self._load_souls()
        entry = {"id": soul_id, "name": name, "content": content}
        souls.append(entry)
        self._save_souls(souls)
        return entry

    def update_soul(self, soul_id: str, name: str | None, content: str | None) -> dict[str, str] | None:
        souls = self._load_souls()
        for s in souls:
            if s.get("id") == soul_id:
                if name is not None:
                    s["name"] = name
                if content is not None:
                    s["content"] = content
                self._save_souls(souls)
                return s
        return None

    def delete_soul(self, soul_id: str) -> bool:
        souls = self._load_souls()
        new = [s for s in souls if s.get("id") != soul_id]
        if len(new) == len(souls):
            return False
        self._save_souls(new)
        return True


_manager: TutorBotManager | None = None


def get_tutorbot_manager() -> TutorBotManager:
    global _manager
    if _manager is None:
        _manager = TutorBotManager()
    return _manager
