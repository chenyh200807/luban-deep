"""Heartbeat service - periodic agent wake-up to check for tasks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from loguru import logger

if TYPE_CHECKING:
    from deeptutor.tutorbot.providers.base import LLMProvider


def _heartbeat_redis() -> "object | None":
    """Reuse the rate-limit Redis (valkey) config for cross-worker coordination.
    Returns None when Redis isn't configured/available (single-worker mode)."""
    backend = str(os.getenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")).strip().lower()
    url = str(os.getenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if backend != "redis" or not url:
        return None
    try:
        import redis

        # Sync client on the event-loop thread — bound the stall if valkey is half-dead.
        return redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    except Exception:  # noqa: BLE001 — any failure → no cross-worker lock (fail-open)
        return None

_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "Report heartbeat decision after reviewing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = nothing to do, run = has active tasks",
                    },
                    "tasks": {
                        "type": "string",
                        "description": "Natural-language summary of active tasks (required for run)",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    Phase 1 (decision): reads HEARTBEAT.md and asks the LLM — via a virtual
    tool call — whether there are active tasks.  This avoids free-text parsing
    and the unreliable HEARTBEAT_OK token.

    Phase 2 (execution): only triggered when Phase 1 returns ``run``.  The
    ``on_execute`` callback runs the task through the full agent loop and
    returns the result to deliver.
    """

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        interval_s: int = 30 * 60,
        enabled: bool = True,
        single_instance_key: str | None = None,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.interval_s = interval_s
        self.enabled = enabled
        # Cross-worker single-instance guard. With uvicorn --workers N, every worker
        # starts its own copy of a bot and thus its own heartbeat loop — without this,
        # the periodic LLM tick (and its memory/notify side effects) fires N times. When
        # set, each tick first claims a short valkey lock for the window so only ONE
        # worker actually runs it. Fail-open: no Redis → behaves as single-worker.
        self._single_instance_key = single_instance_key
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    async def _decide(self, content: str) -> tuple[str, str]:
        """Phase 1: ask LLM to decide skip/run via virtual tool call.

        Returns (action, tasks) where action is 'skip' or 'run'.
        """
        response = await self.provider.chat_with_retry(
            messages=[
                {"role": "system", "content": "You are a heartbeat agent. Call the heartbeat tool to report your decision."},
                {"role": "user", "content": (
                    "Review the following HEARTBEAT.md and decide whether there are active tasks.\n\n"
                    f"{content}"
                )},
            ],
            tools=_HEARTBEAT_TOOL,
            model=self.model,
        )

        if not response.has_tool_calls:
            return "skip", ""

        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("tasks", "")

    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return
        if self._running:
            logger.warning("Heartbeat already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Heartbeat started (every {}s)", self.interval_s)

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat error: {}", e)

    def _claim_tick_window(self) -> bool:
        """True if this worker may run this tick. With a single-instance key + valkey,
        only one worker wins the window (SET NX); others skip. Fail-open (no Redis or
        error → True) so a single-worker / Redis-down deployment still ticks."""
        if not self._single_instance_key:
            return True
        client = _heartbeat_redis()
        if client is None:
            return True
        try:
            # Lock lives ~one interval so the holder owns this window and it expires
            # before the next, letting whichever worker fires first next window re-claim.
            ttl = max(60, int(self.interval_s) - 30)
            got = client.set(f"deeptutor:tutorbot-hb:{self._single_instance_key}", "1", nx=True, ex=ttl)
            return bool(got)
        except Exception:  # noqa: BLE001 — Redis hiccup → fail-open (run)
            return True

    async def _tick(self) -> None:
        """Execute a single heartbeat tick."""
        from deeptutor.tutorbot.utils.evaluator import evaluate_response

        if not self._claim_tick_window():
            logger.debug("Heartbeat: another worker owns this window; skipping")
            return

        content = self._read_heartbeat_file()
        if not content:
            logger.debug("Heartbeat: HEARTBEAT.md missing or empty")
            return

        logger.info("Heartbeat: checking for tasks...")

        try:
            action, tasks = await self._decide(content)

            if action != "run":
                logger.info("Heartbeat: OK (nothing to report)")
                return

            logger.info("Heartbeat: tasks found, executing...")
            if self.on_execute:
                response = await self.on_execute(tasks)

                if response:
                    should_notify = await evaluate_response(
                        response, tasks, self.provider, self.model,
                    )
                    if should_notify and self.on_notify:
                        logger.info("Heartbeat: completed, delivering response")
                        await self.on_notify(response)
                    else:
                        logger.info("Heartbeat: silenced by post-run evaluation")
        except Exception:
            logger.exception("Heartbeat execution failed")

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat."""
        content = self._read_heartbeat_file()
        if not content:
            return None
        action, tasks = await self._decide(content)
        if action != "run" or not self.on_execute:
            return None
        return await self.on_execute(tasks)
