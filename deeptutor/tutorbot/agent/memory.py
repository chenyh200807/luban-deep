"""Memory system for persistent agent memory."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from deeptutor.tutorbot.utils.helpers import ensure_dir, estimate_message_tokens, estimate_prompt_tokens_chain

if TYPE_CHECKING:
    from deeptutor.tutorbot.providers.base import LLMProvider
    from deeptutor.tutorbot.session.manager import Session, SessionManager


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


def _ensure_text(value: Any) -> str:
    """Normalize tool-call payload values to text for file storage."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _normalize_save_memory_args(args: Any) -> dict[str, Any] | None:
    """Normalize provider tool-call arguments to the expected dict shape."""
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, list):
        return args[0] if args and isinstance(args[0], dict) else None
    return args if isinstance(args, dict) else None

_TOOL_CHOICE_ERROR_MARKERS = (
    "tool_choice",
    "toolchoice",
    "does not support",
    'should be ["none", "auto"]',
)


def _is_tool_choice_unsupported(content: str | None) -> bool:
    """Detect provider errors caused by forced tool_choice being unsupported."""
    text = (content or "").lower()
    return any(m in text for m in _TOOL_CHOICE_ERROR_MARKERS)


class MemoryStore:
    """Two-layer memory: long-term facts + grep-searchable history log.

    Reads/writes go to ``data/memory/`` (shared with DeepTutor) — PROFILE.md
    for long-term facts, SUMMARY.md for history.  Standalone fallback uses
    workspace/memory/MEMORY.md + HISTORY.md when no shared dir is given.
    """

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, workspace: Path, *, shared_memory_dir: Path | None = None):
        if shared_memory_dir:
            self.memory_dir = ensure_dir(shared_memory_dir)
            self.memory_file = self.memory_dir / "PROFILE.md"
            self.history_file = self.memory_dir / "SUMMARY.md"
        else:
            self.memory_dir = ensure_dir(workspace / "memory")
            self.memory_file = self.memory_dir / "MEMORY.md"
            self.history_file = self.memory_dir / "HISTORY.md"
        self._consecutive_failures = 0

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    async def consolidate(
        self,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """Consolidate the provided message chunk into MEMORY.md + HISTORY.md."""
        if not messages:
            return True

        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{self._format_messages(messages)}"""

        chat_messages = [
            {"role": "system", "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."},
            {"role": "user", "content": prompt},
        ]

        try:
            forced = {"type": "function", "function": {"name": "save_memory"}}
            response = await provider.chat_with_retry(
                messages=chat_messages,
                tools=_SAVE_MEMORY_TOOL,
                model=model,
                tool_choice=forced,
            )

            if response.finish_reason == "error" and _is_tool_choice_unsupported(
                response.content
            ):
                logger.warning("Forced tool_choice unsupported, retrying with auto")
                response = await provider.chat_with_retry(
                    messages=chat_messages,
                    tools=_SAVE_MEMORY_TOOL,
                    model=model,
                    tool_choice="auto",
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory consolidation: LLM did not call save_memory "
                    "(finish_reason={}, content_len={}, content_preview={})",
                    response.finish_reason,
                    len(response.content or ""),
                    (response.content or "")[:200],
                )
                return self._fail_or_raw_archive(messages)

            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if args is None:
                logger.warning("Memory consolidation: unexpected save_memory arguments")
                return self._fail_or_raw_archive(messages)

            if "history_entry" not in args or "memory_update" not in args:
                logger.warning("Memory consolidation: save_memory payload missing required fields")
                return self._fail_or_raw_archive(messages)

            entry = args["history_entry"]
            update = args["memory_update"]

            if entry is None or update is None:
                logger.warning("Memory consolidation: save_memory payload contains null required fields")
                return self._fail_or_raw_archive(messages)

            entry = _ensure_text(entry).strip()
            if not entry:
                logger.warning("Memory consolidation: history_entry is empty after normalization")
                return self._fail_or_raw_archive(messages)

            self.append_history(entry)
            update = _ensure_text(update)
            if update != current_memory:
                self.write_long_term(update)

            self._consecutive_failures = 0
            logger.info("Memory consolidation done for {} messages", len(messages))
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return self._fail_or_raw_archive(messages)

    def _fail_or_raw_archive(self, messages: list[dict]) -> bool:
        """Increment failure count; after threshold, raw-archive messages and return True."""
        self._consecutive_failures += 1
        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False
        self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    def _raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages to HISTORY.md without LLM summarization."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.append_history(
            f"[{ts}] [RAW] {len(messages)} messages\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )


class MemoryConsolidator:
    """Owns consolidation policy, locking, and session offset updates."""

    _MAX_CONSOLIDATION_ROUNDS = 5
    # Above this many already-persisted messages, seed the per-message token
    # table on a worker thread so a cold session's first turn does not block the
    # event loop on one big synchronous BPE pass.
    _COLD_START_MESSAGE_THRESHOLD = 64

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        shared_memory_dir: Path | None = None,
        consolidation_model: str | None = None,
    ):
        self.store = MemoryStore(workspace, shared_memory_dir=shared_memory_dir)
        self.provider = provider
        # ``model`` is the main-loop token-estimation ANCHOR (tokenizer alignment
        # for prompt-size / consolidation-boundary decisions) and MUST NOT drift
        # with the light tier. ``consolidation_model`` (optional) only swaps the
        # model used for the consolidation LLM call itself. None => use self.model.
        self.model = model
        self.consolidation_model = (consolidation_model or "").strip() or None
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: dict[str, asyncio.Lock] = {}
        # Process-local, discardable memoization of prompt-size estimation.
        # Keyed by ``session.key``; each entry is
        # ``{"per_msg": list[int], "base": int, "base_sig": tuple | None}`` where
        # ``per_msg`` is index-aligned to ``session.messages``.  This is pure
        # derived state: never persisted, never written into any message dict,
        # never part of any contract.  Losing it forces one recompute.  The sole
        # consolidation decider remains ``maybe_consolidate_by_tokens``; this
        # only changes HOW the same input is computed, not WHO decides.
        self._token_cache: dict[str, dict[str, Any]] = {}

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    def release_lock(self, session_key: str) -> bool:
        """Release an idle per-session consolidation lock after session teardown."""
        lock = self._locks.get(session_key)
        if lock is None:
            return False
        if lock.locked():
            return False
        waiters = getattr(lock, "_waiters", None)
        if waiters and any(not waiter.cancelled() for waiter in waiters):
            return False
        self._locks.pop(session_key, None)
        return True

    async def consolidate_messages(self, messages: list[dict[str, object]]) -> bool:
        """Archive a selected message chunk into persistent memory."""
        return await self.store.consolidate(
            messages, self.provider, self.consolidation_model or self.model
        )

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        # Reuse the per-message token counts populated by
        # ``_incremental_prompt_tokens`` (index-aligned to ``session.messages``)
        # so boundary selection does not re-encode every message; fall back to a
        # direct estimate only on a cache miss.
        per_msg = self._token_cache.get(session.key, {}).get("per_msg") or []

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            if idx < len(per_msg):
                removed_tokens += per_msg[idx]
            else:
                removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=0)
        channel, chat_id = (session.key.split(":", 1) if ":" in session.key else (None, None))
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    def _base_signature(self) -> tuple[int, int, int]:
        """Cheap fingerprint of everything the constant (non-message) prompt
        segment depends on: the persisted memory files (folded into the system
        prompt) and the tool schema.  When unchanged, the cached ``base`` is
        reused; when it changes (e.g. a consolidation round rewrote MEMORY.md)
        the base is recomputed.  O(1) in message count."""
        def _mtime(path: Path) -> int:
            try:
                return path.stat().st_mtime_ns
            except OSError:
                return -1

        tools_len = len(json.dumps(self._get_tool_definitions(), ensure_ascii=False))
        return (
            _mtime(self.store.memory_file),
            _mtime(self.store.history_file),
            tools_len,
        )

    def _estimate_base_tokens(self, session: Session) -> int:
        """Estimate the constant prompt segment (system prompt + tools + probe
        scaffolding) against an EMPTY history.  Depends only on system/tool
        material, so it is O(1) in message count and safe to compute on the hot
        path when the signature changes."""
        channel, chat_id = (
            session.key.split(":", 1) if ":" in session.key else (None, None)
        )
        probe_messages = self._build_messages(
            history=[],
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        base, _ = estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )
        return base

    @staticmethod
    def _counts_toward_prompt(message: dict) -> bool:
        """Deterministic per-message mirror of the stable-history DROP rules.

        ``Session.stable_messages()`` always drops tool results (role not in
        user/assistant) and assistant tool_call intermediates — those rules are
        decidable per message, so the incremental table can record 0 for them
        without ever re-walking history.  Superseded assistant messages are
        still counted (their stability depends on later messages), which keeps
        the incremental value an UPPER BOUND while removing the tool-payload
        bloat that made tool-dense sessions consolidate far too early
        (observed +458% over-estimate before this refinement).
        """
        role = message.get("role")
        if role not in ("user", "assistant"):
            return False
        if role == "assistant" and message.get("tool_calls"):
            return False
        return True

    async def _incremental_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size incrementally, re-encoding only messages
        appended since the previous call.

        This turns the per-turn ``O(all messages)`` BPE pass done by
        ``estimate_session_prompt_tokens`` into ``O(new messages)`` via the
        process-local ``self._token_cache`` (see ``__init__``).

        Direction safety: the returned value is an UPPER BOUND on
        ``estimate_session_prompt_tokens``.  The per-message sum walks the raw,
        append-only ``session.messages`` (including tool-intermediate turns),
        whereas the full estimator walks the collapsed *stable* history
        (``get_history`` drops those intermediates).  ``estimate_message_tokens``
        also counts a message's ``tool_calls``/``name`` payload that the flat
        chain estimate omits.  Both effects make the incremental value ``>=`` the
        full value — over-counting is safe here because it only makes us
        consolidate slightly EARLY, never lets the context window overflow.

        The cache is pure discardable derived state (never persisted, never in a
        message dict, never in a contract); losing it forces one recompute and
        does not change WHO decides consolidation.
        """
        cache = self._token_cache.setdefault(
            session.key, {"per_msg": [], "base": -1, "base_sig": None}
        )
        per_msg: list[int] = cache["per_msg"]
        msgs = session.messages

        # clear()/truncation shrinks the append-only list — drop the stale table
        # so we never read token counts that belonged to since-removed messages.
        if len(per_msg) > len(msgs):
            per_msg.clear()

        # Cold start on a long, already-persisted session: seed the whole table
        # once off the event loop (we hold the per-session consolidation lock, so
        # no concurrent writer mutates this cache).
        if not per_msg and len(msgs) > self._COLD_START_MESSAGE_THRESHOLD:
            snapshot = list(msgs)
            per_msg.extend(
                await asyncio.to_thread(
                    lambda: [
                        estimate_message_tokens(m) if self._counts_toward_prompt(m) else 0
                        for m in snapshot
                    ]
                )
            )

        # Steady state: encode only the messages appended since the last call.
        for idx in range(len(per_msg), len(msgs)):
            message = msgs[idx]
            per_msg.append(
                estimate_message_tokens(message) if self._counts_toward_prompt(message) else 0
            )

        base_sig = self._base_signature()
        if cache["base_sig"] != base_sig:
            cache["base"] = self._estimate_base_tokens(session)
            cache["base_sig"] = base_sig

        tail = sum(per_msg[session.last_consolidated:])
        return cache["base"] + tail, "tiktoken_incremental"

    async def archive_unconsolidated(self, session: Session) -> bool:
        """Archive the full unconsolidated tail for /new-style session rollover."""
        lock = self.get_lock(session.key)
        async with lock:
            snapshot = session.messages[session.last_consolidated:]
            if not snapshot:
                return True
            return await self.consolidate_messages(snapshot)

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within half the context window."""
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            target = self.context_window_tokens // 2
            estimated, source = await self._incremental_prompt_tokens(session)
            if estimated <= 0:
                return
            if estimated < self.context_window_tokens:
                logger.debug(
                    "Token consolidation idle {}: {}/{} via {}",
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                )
                return

            for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(
                        "Token consolidation: no safe boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                end_idx = boundary[0]
                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                    round_num,
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    len(chunk),
                )
                if not await self.consolidate_messages(chunk):
                    return
                session.last_consolidated = end_idx
                self.sessions.save(session)

                estimated, source = await self._incremental_prompt_tokens(session)
                if estimated <= 0:
                    return
