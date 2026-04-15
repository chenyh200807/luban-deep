from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from deeptutor.logging import get_logger
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.tutorbot import get_tutorbot_manager

from .flusher import LearnerStateOutboxFlusher
from .heartbeat.scheduler import LearnerHeartbeatScheduler
from .supabase_writer import LearnerStateSupabaseWriter

logger = get_logger("LearnerStateRuntime")


@dataclass(frozen=True)
class LearnerStateRuntimeConfig:
    outbox_flush_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 60.0
    outbox_flush_limit: int = 20
    heartbeat_limit: int | None = None


class LearnerStateRuntime:
    """Own the learner-state background loops for outbox flush and heartbeat scheduling."""

    def __init__(
        self,
        *,
        flusher: LearnerStateOutboxFlusher | None,
        heartbeat_scheduler: LearnerHeartbeatScheduler | None,
        writer: LearnerStateSupabaseWriter | None = None,
        config: LearnerStateRuntimeConfig | None = None,
    ) -> None:
        self._flusher = flusher
        self._heartbeat_scheduler = heartbeat_scheduler
        self._writer = writer
        self._config = config or LearnerStateRuntimeConfig()
        self._stop_event: asyncio.Event | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and any(not task.done() for task in self._tasks)

    async def start(self) -> None:
        if self._started:
            return

        self._stop_event = asyncio.Event()
        self._tasks = []
        self._started = True

        if self._flusher is not None:
            self._tasks.append(asyncio.create_task(self._run_outbox_loop(), name="learner-state-outbox-flusher"))
        if self._heartbeat_scheduler is not None:
            self._tasks.append(
                asyncio.create_task(self._run_heartbeat_loop(), name="learner-state-heartbeat-scheduler")
            )

        logger.info(
            f"LearnerState runtime started: flusher={self._flusher is not None} "
            f"heartbeat={self._heartbeat_scheduler is not None}"
        )

    async def stop(self) -> None:
        if not self._started:
            await self._close_writer()
            return

        assert self._stop_event is not None
        self._stop_event.set()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False
        self._stop_event = None
        await self._close_writer()
        logger.info("LearnerState runtime stopped")

    async def _run_outbox_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self._flusher.flush_once(limit=self._config.outbox_flush_limit)  # type: ignore[union-attr]
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"LearnerState outbox flush loop failed: {exc}")
            await self._sleep_until_stop(self._config.outbox_flush_interval_seconds)

    async def _run_heartbeat_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self._heartbeat_scheduler.run_once(  # type: ignore[union-attr]
                    limit=self._config.heartbeat_limit
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"LearnerState heartbeat loop failed: {exc}")
            await self._sleep_until_stop(self._config.heartbeat_interval_seconds)

    async def _sleep_until_stop(self, timeout_seconds: float) -> None:
        assert self._stop_event is not None
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.0, float(timeout_seconds)))
        except asyncio.TimeoutError:
            return

    async def _close_writer(self) -> None:
        if self._writer is None:
            return
        close = getattr(self._writer, "aclose", None)
        if not callable(close):
            return
        result = close()
        if inspect.isawaitable(result):
            await result


class LearnerHeartbeatExecutor:
    """Execute learner heartbeat jobs through the existing TutorBot runtime."""

    def __init__(self, tutorbot_manager: Any | None = None) -> None:
        self._tutorbot_manager = tutorbot_manager

    @property
    def tutorbot_manager(self) -> Any:
        return self._tutorbot_manager or get_tutorbot_manager()

    @staticmethod
    def _build_prompt(job: Any) -> str:
        policy = dict(getattr(job, "policy_json", {}) or {})
        prompt = str(policy.get("prompt") or "").strip()
        if prompt:
            return prompt
        cadence = str(policy.get("cadence") or "daily").strip() or "daily"
        return (
            "请基于当前学员的长期 learner state，执行一次主动学习 heartbeat。"
            f"当前 cadence 为 {cadence}。"
            "如果适合触达，就生成一段简短、具体、可执行的提醒；"
            "如果不适合触达，也请明确说明原因。"
        )

    async def __call__(self, job: Any) -> dict[str, Any]:
        conversation_id = f"learner-heartbeat:{job.user_id}:{job.channel}"
        response = await self.tutorbot_manager.send_message(
            bot_id=job.bot_id,
            content=self._build_prompt(job),
            chat_id=conversation_id,
            session_key=f"learner-heartbeat:{job.bot_id}:{job.user_id}:{job.channel}",
            session_metadata={
                "user_id": job.user_id,
                "source": "learner_heartbeat",
                "conversation_id": conversation_id,
                "title": "Learner Heartbeat",
                "channel": job.channel,
            },
        )
        message = str(response or "").strip()
        return {
            "message": message,
            "response_len": len(message),
            "delivery_state": "sent" if message else "empty",
        }


def create_default_learner_state_runtime(
    path_service: PathService | None = None,
) -> LearnerStateRuntime:
    from .service import LearnerStateService

    service = LearnerStateService(path_service=path_service or get_path_service())
    writer = LearnerStateSupabaseWriter()
    flusher = None
    if writer.is_configured:
        flusher = LearnerStateOutboxFlusher(service.outbox_service, writer)
    heartbeat_scheduler = LearnerHeartbeatScheduler(
        service=service,
        executor=LearnerHeartbeatExecutor(),
    )
    return LearnerStateRuntime(
        flusher=flusher,
        heartbeat_scheduler=heartbeat_scheduler,
        writer=writer if writer.is_configured else None,
    )


__all__ = [
    "LearnerHeartbeatExecutor",
    "LearnerStateRuntime",
    "LearnerStateRuntimeConfig",
    "create_default_learner_state_runtime",
]
