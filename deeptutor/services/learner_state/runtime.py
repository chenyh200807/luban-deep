from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from deeptutor.logging import get_logger
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.tutorbot import get_tutorbot_manager

from .flusher import LearnerStateOutboxFlusher
from .heartbeat import LearnerHeartbeatArbitrationHints
from .heartbeat.scheduler import LearnerHeartbeatScheduler
from .heartbeat.store import LearnerHeartbeatJob
from .study_plan import build_study_plan_from_learner_snapshot, format_study_plan_for_prompt
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

    def __init__(self, tutorbot_manager: Any | None = None, learner_state_service: Any | None = None) -> None:
        self._tutorbot_manager = tutorbot_manager
        self._learner_state_service = learner_state_service

    @property
    def tutorbot_manager(self) -> Any:
        return self._tutorbot_manager or get_tutorbot_manager()

    def _build_prompt(self, job: Any) -> str:
        policy = dict(getattr(job, "policy_json", {}) or {})
        prompt = str(policy.get("prompt") or "").strip()
        if prompt:
            return prompt
        cadence = str(policy.get("cadence") or "daily").strip() or "daily"
        profile_text = ""
        progress_text = ""
        study_plan_text = ""
        goals_text = ""
        if self._learner_state_service is not None:
            try:
                snapshot = self._learner_state_service.read_snapshot(job.user_id)
            except Exception:
                snapshot = None
            if snapshot is not None:
                profile = dict(getattr(snapshot, "profile", {}) or {})
                progress = dict(getattr(snapshot, "progress", {}) or {})
                goals = list(self._learner_state_service.read_goals(job.user_id) or [])
                focus_topic = str(profile.get("focus_topic") or "").strip()
                exam_date = str(profile.get("exam_date") or "").strip()
                difficulty = str(profile.get("difficulty_preference") or "").strip()
                if focus_topic or exam_date or difficulty:
                    fragments = []
                    if focus_topic:
                        fragments.append(f"当前聚焦：{focus_topic}")
                    if exam_date:
                        fragments.append(f"考试日期：{exam_date}")
                    if difficulty:
                        fragments.append(f"难度偏好：{difficulty}")
                    profile_text = "\n学员画像：\n- " + "\n- ".join(fragments)
                today = dict(progress.get("today") or {})
                weak_points = list((progress.get("knowledge_map") or {}).get("weak_points") or [])
                progress_lines = []
                if today:
                    progress_lines.append(
                        f"今日完成 {int(today.get('today_done') or 0)} / {int(today.get('daily_target') or 0)}"
                    )
                last_practiced_at = str(progress.get("last_practiced_at") or "").strip()
                if last_practiced_at:
                    progress_lines.append(f"最近学习：{last_practiced_at}")
                if weak_points:
                    progress_lines.append("薄弱点：" + "、".join(str(item).strip() for item in weak_points[:3] if str(item).strip()))
                if progress_lines:
                    progress_text = "\n学习进度：\n- " + "\n- ".join(progress_lines)
                study_plan_text = format_study_plan_for_prompt(
                    build_study_plan_from_learner_snapshot(snapshot)
                )
            else:
                goals = []
            if goals:
                goal_lines = []
                for item in goals[:3]:
                    title = str(item.get("title") or "").strip()
                    progress = item.get("progress", 0)
                    deadline = str(item.get("deadline") or "").strip()
                    fragment = title or "未命名目标"
                    if progress not in {"", None}:
                        fragment += f"，进度 {progress}"
                    if deadline:
                        fragment += f"，截止 {deadline}"
                    goal_lines.append(fragment)
                if goal_lines:
                    goals_text = "\n当前学员目标：\n- " + "\n- ".join(goal_lines)
        return (
            "请基于当前学员的长期 learner state，执行一次主动学习 heartbeat。"
            f"当前 cadence 为 {cadence}。"
            "如果适合触达，就生成一段简短、具体、可执行的提醒；"
            "如果不适合触达，也请明确说明原因。"
            f"{profile_text}{progress_text}{study_plan_text}{goals_text}"
        )

    async def __call__(self, job: Any) -> dict[str, Any]:
        conversation_id = f"learner-heartbeat:{job.user_id}:{job.channel}"
        session_key = f"learner-heartbeat:{job.bot_id}:{job.user_id}:{job.channel}"
        response = await self.tutorbot_manager.send_message(
            bot_id=job.bot_id,
            content=self._build_prompt(job),
            chat_id=conversation_id,
            session_key=session_key,
            session_metadata={
                "user_id": job.user_id,
                "source": "learner_heartbeat",
                "conversation_id": conversation_id,
                "title": "Learner Heartbeat",
                "channel": job.channel,
            },
        )
        message = str(response or "").strip()
        delivery_state = "sent" if message else "empty"
        return {
            "message": message,
            "response_len": len(message),
            "delivery_state": delivery_state,
            "delivery": {
                "state": delivery_state,
                "message": message,
                "message_len": len(message),
                "conversation_id": conversation_id,
                "channel": job.channel,
                "bot_id": job.bot_id,
                "user_id": job.user_id,
            },
            "audit": {
                "job_id": job.job_id,
                "user_id": job.user_id,
                "bot_id": job.bot_id,
                "channel": job.channel,
                "conversation_id": conversation_id,
                "session_key": session_key,
                "source": "learner_heartbeat",
                "status": "ok",
                "success": True,
                "delivery_state": delivery_state,
                "trigger_reason": "learner_state_due",
                "response_len": len(message),
            },
        }


def _default_heartbeat_hint_resolver(learner_state_service: Any):
    def _resolve_active_plan_bot_id(user_id: str) -> str | None:
        plan_service = getattr(learner_state_service, "_learning_plan_service", None)
        if plan_service is None or not hasattr(plan_service, "list_plans"):
            return None
        try:
            plans = list(plan_service.list_plans() or [])
        except Exception:
            return None
        active_candidates = [
            item
            for item in plans
            if str(item.get("user_id") or "").strip() == user_id
            and str(item.get("source_bot_id") or "").strip()
            and str(item.get("status") or "").strip() in {"initialized", "in_progress", "ready"}
        ]
        if not active_candidates:
            return None
        active_candidates.sort(
            key=lambda item: float(item.get("updated_at", item.get("created_at", 0.0)) or 0.0),
            reverse=True,
        )
        return str(active_candidates[0].get("source_bot_id") or "").strip() or None

    def _resolve_recent_interaction_sources(user_id: str) -> dict[str, str]:
        if not hasattr(learner_state_service, "list_memory_events"):
            return {}
        try:
            events = list(learner_state_service.list_memory_events(user_id, limit=50) or [])
        except Exception:
            return {}
        resolved: dict[str, str] = {}
        for event in reversed(events):
            bot_id = str(getattr(event, "source_bot_id", "") or "").strip()
            source_feature = str(getattr(event, "source_feature", "") or "").strip()
            if not bot_id or bot_id in resolved or not source_feature:
                continue
            resolved[bot_id] = source_feature
        return resolved

    def _resolve_overlay_overrides(user_id: str, jobs: list[LearnerHeartbeatJob]) -> dict[str, dict[str, Any]]:
        try:
            from .overlay_service import get_bot_learner_overlay_service

            overlay_service = get_bot_learner_overlay_service()
        except Exception:
            return {}
        overrides: dict[str, dict[str, Any]] = {}
        for job in jobs:
            bot_id = str(job.bot_id or "").strip()
            if not bot_id or bot_id in overrides:
                continue
            try:
                if hasattr(overlay_service, "resolve_heartbeat_inputs"):
                    payload = dict(overlay_service.resolve_heartbeat_inputs(bot_id, user_id) or {})
                    candidate = dict(payload.get("heartbeat_override_candidate") or {})
                else:
                    payload = dict(overlay_service.read_overlay(bot_id, user_id) or {})
                    candidate = dict(payload.get("heartbeat_override_candidate") or {})
            except Exception:
                continue
            if candidate:
                overrides[bot_id] = candidate
        return overrides

    def _compute_goal_urgency(goal: dict[str, Any]) -> int:
        if not isinstance(goal, dict):
            return 0
        try:
            progress = int(goal.get("progress", 0) or 0)
        except Exception:
            progress = 0
        progress = max(0, min(100, progress))
        urgency = 0
        deadline = str(goal.get("deadline") or "").strip()
        if deadline:
            try:
                deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
                days_left = (deadline_dt.astimezone() - datetime.now(timezone.utc).astimezone()).total_seconds() / 86400.0
                if days_left <= 3:
                    urgency += 6
                elif days_left <= 7:
                    urgency += 4
                elif days_left <= 14:
                    urgency += 2
            except Exception:
                pass
        if progress < 30:
            urgency += 3
        elif progress < 60:
            urgency += 2
        elif progress < 85:
            urgency += 1
        return max(0, min(10, urgency))

    def _resolve_goal_urgency_by_bot_id(
        user_id: str,
        jobs: list[LearnerHeartbeatJob],
        *,
        active_plan_bot_id: str | None,
    ) -> dict[str, int]:
        if not hasattr(learner_state_service, "read_goals"):
            return {}
        try:
            goals = list(learner_state_service.read_goals(user_id) or [])
        except Exception:
            return {}
        if not goals:
            return {}
        max_urgency = max((_compute_goal_urgency(goal) for goal in goals if isinstance(goal, dict)), default=0)
        if max_urgency <= 0:
            return {}
        job_bot_ids = [str(job.bot_id or "").strip() for job in jobs if str(job.bot_id or "").strip()]
        if not job_bot_ids:
            return {}
        if active_plan_bot_id and active_plan_bot_id in job_bot_ids:
            return {active_plan_bot_id: max_urgency}
        if len(job_bot_ids) == 1:
            return {job_bot_ids[0]: max_urgency}
        return {bot_id: max_urgency for bot_id in job_bot_ids}

    def _resolve_recently_contacted_until(jobs: list[LearnerHeartbeatJob]) -> dict[str, datetime]:
        resolved: dict[str, datetime] = {}
        for job in jobs:
            bot_id = str(job.bot_id or "").strip()
            if not bot_id or job.last_run_at is None:
                continue
            try:
                cooldown_hours = max(0, int(dict(job.policy_json or {}).get("cooldown_hours") or 0))
            except Exception:
                cooldown_hours = 0
            if cooldown_hours <= 0:
                continue
            resolved[bot_id] = job.last_run_at + timedelta(hours=cooldown_hours)
        return resolved

    async def _resolver(user_id: str, jobs: list[LearnerHeartbeatJob]) -> LearnerHeartbeatArbitrationHints:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return LearnerHeartbeatArbitrationHints()
        active_plan_bot_id = _resolve_active_plan_bot_id(normalized_user_id)
        return LearnerHeartbeatArbitrationHints(
            active_plan_bot_id=active_plan_bot_id,
            learner_goal_urgency_by_bot_id=_resolve_goal_urgency_by_bot_id(
                normalized_user_id,
                jobs,
                active_plan_bot_id=active_plan_bot_id,
            ),
            recent_interaction_source_by_bot_id=_resolve_recent_interaction_sources(normalized_user_id),
            overlay_heartbeat_override_by_bot_id=_resolve_overlay_overrides(normalized_user_id, jobs),
            recently_contacted_until_by_bot_id=_resolve_recently_contacted_until(jobs),
        )

    return _resolver


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
        executor=LearnerHeartbeatExecutor(learner_state_service=service),
        hint_resolver=_default_heartbeat_hint_resolver(service),
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
    "_default_heartbeat_hint_resolver",
    "create_default_learner_state_runtime",
]
