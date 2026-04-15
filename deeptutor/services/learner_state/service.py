from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.learning_plan import LearningPlanService
from deeptutor.services.learner_state.heartbeat import (
    LearnerHeartbeatJob,
    LearnerHeartbeatJobService,
)
from deeptutor.services.learner_state.outbox import (
    LearnerStateOutbox as LearnerStateOutboxService,
    LearnerStateOutboxItem,
)
from deeptutor.services.path_service import PathService, get_path_service

llm_stream: Any | None = None

LearnerStateEventKind = Literal["turn", "guide", "notebook", "progress", "manual"]

_NO_CHANGE = "NO_CHANGE"
_LOW_SIGNAL_TURN_PATTERNS = (
    "你好",
    "您好",
    "在吗",
    "在不",
    "hi",
    "hello",
    "hey",
    "哈喽",
    "嗨",
)
_NON_LEARNING_ACCOUNT_HINTS = ("点数", "余额", "会员", "points", "balance", "credit")
_LEARNING_HINTS = (
    "题",
    "知识",
    "知识点",
    "案例",
    "复习",
    "学习",
    "错题",
    "怎么",
    "为什么",
    "承载",
    "沉降",
    "施工",
    "质量",
    "安全",
    "工期",
    "索赔",
    "规范",
)
_FILENAMES = {
    "profile": "PROFILE.json",
    "summary": "SUMMARY.md",
    "progress": "PROGRESS.json",
    "events": "MEMORY_EVENTS.jsonl",
}


@dataclass
class LearnerStateEvent:
    event_id: str
    user_id: str
    source_feature: str
    source_id: str
    source_bot_id: str | None
    memory_kind: str
    payload_json: dict[str, Any]
    dedupe_key: str
    created_at: str


@dataclass
class LearnerStateSnapshot:
    user_id: str
    profile: dict[str, Any]
    summary: str
    progress: dict[str, Any]
    memory_events: list[LearnerStateEvent]
    profile_updated_at: str | None
    summary_updated_at: str | None
    progress_updated_at: str | None
    memory_events_updated_at: str | None


@dataclass
class LearnerStateUpdateResult:
    content: str
    changed: bool
    updated_at: str | None


@dataclass
class LearningPlanRecord:
    plan_id: str
    user_id: str
    source_bot_id: str | None
    source_material_refs_json: list[dict[str, Any]]
    knowledge_points_json: list[dict[str, Any]]
    status: str
    current_index: int
    completion_summary_md: str
    created_at: str
    updated_at: str


@dataclass
class LearningPlanPageRecord:
    plan_id: str
    page_index: int
    page_status: str
    html_content: str
    error_message: str
    generated_at: str | None


class LearnerStateService:
    """Single source of truth for learner profile, summary, progress and events."""

    def __init__(
        self,
        path_service: PathService | None = None,
        member_service: Any | None = None,
        outbox_service: LearnerStateOutboxService | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._member_service = member_service or self._default_member_service()
        self._outbox_service = outbox_service or LearnerStateOutboxService(path_service=self._path_service)
        self._learning_plan_service = LearningPlanService(path_service=self._path_service)
        self._heartbeat_job_service = LearnerHeartbeatJobService(path_service=self._path_service)
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def _learner_root(self) -> Path:
        getter = getattr(self._path_service, "get_learner_state_root", None)
        if callable(getter):
            return Path(getter())
        return self._path_service.get_user_root() / "learner_state"

    def _user_dir(self, user_id: str) -> Path:
        normalized = _normalize_user_id(user_id)
        return self._learner_root / normalized

    def _path(self, user_id: str, which: str) -> Path:
        return self._user_dir(user_id) / _FILENAMES[which]

    def _file_updated_at(self, user_id: str, which: str) -> str | None:
        path = self._path(user_id, which)
        if not path.exists():
            return None
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        except Exception:
            return None

    def _safe_lock(self, user_id: str) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    @property
    def outbox_service(self) -> LearnerStateOutboxService:
        return self._outbox_service

    def _enqueue_summary_refresh(
        self,
        *,
        user_id: str,
        summary_md: str,
        source_feature: str,
        source_id: str,
        source_bot_id: str | None = None,
    ) -> LearnerStateOutboxItem:
        dedupe_key = self._default_dedupe_key(
            user_id,
            source_feature=source_feature,
            source_id=source_id,
            memory_kind="summary_refresh",
            payload_json={"summary_md": summary_md},
        )
        return self._outbox_service.enqueue(
            user_id=user_id,
            event_type="summary_refresh",
            payload_json={
                "user_id": user_id,
                "summary_md": str(summary_md or "").strip(),
                "source_feature": str(source_feature or "").strip() or "manual",
                "source_id": str(source_id or "").strip() or "unknown",
                "source_bot_id": str(source_bot_id or "").strip() or None,
                "updated_at": _iso_now(),
            },
            dedupe_key=dedupe_key,
        )

    def _safe_member_profile(self, user_id: str) -> dict[str, Any]:
        try:
            profile = dict(self._member_service.get_profile(user_id) or {})
        except Exception:
            profile = {"user_id": user_id, "display_name": user_id}
        profile.setdefault("user_id", user_id)
        profile.setdefault("display_name", user_id)
        return profile

    @staticmethod
    def _default_member_service() -> Any:
        from deeptutor.services.member_console import get_member_console_service

        return get_member_console_service()

    def _safe_member_progress(self, user_id: str) -> dict[str, Any]:
        progress: dict[str, Any] = {}
        try:
            progress["today"] = dict(self._member_service.get_today_progress(user_id) or {})
        except Exception:
            progress["today"] = {}
        try:
            progress["chapters"] = list(self._member_service.get_chapter_progress(user_id) or [])
        except Exception:
            progress["chapters"] = []
        return progress

    def _read_profile_raw(self, user_id: str) -> dict[str, Any]:
        path = self._path(user_id, "profile")
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8").strip()
            return dict(json.loads(content)) if content else {}
        except Exception:
            return {}

    def _read_summary_raw(self, user_id: str) -> str:
        path = self._path(user_id, "summary")
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _read_progress_raw(self, user_id: str) -> dict[str, Any]:
        path = self._path(user_id, "progress")
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8").strip()
            return dict(json.loads(content)) if content else {}
        except Exception:
            return {}

    def _ensure_seed_state(self, user_id: str) -> None:
        profile_path = self._path(user_id, "profile")
        progress_path = self._path(user_id, "progress")
        summary_path = self._path(user_id, "summary")

        profile = self._read_profile_raw(user_id)
        if not profile:
            profile = self._safe_member_profile(user_id)
            self.write_profile(user_id, profile)

        progress = self._read_progress_raw(user_id)
        if not progress:
            progress = self._seed_progress(profile, user_id, self._safe_member_progress(user_id))
            self.write_progress(user_id, progress)

        if not summary_path.exists() or not self._read_summary_raw(user_id).strip():
            summary = self._seed_summary(profile, progress)
            self.write_summary(user_id, summary)

        if not profile_path.exists() and profile:
            self.write_profile(user_id, profile)
        if not progress_path.exists() and progress:
            self.write_progress(user_id, progress)

        self.ensure_default_job(user_id)

    def read_profile(self, user_id: str) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        self._ensure_seed_state(normalized)
        return self._read_profile_raw(normalized)

    def write_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        path = self._path(normalized, "profile")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _json_dump(profile)
        path.write_text(payload, encoding="utf-8")
        try:
            self.ensure_default_job(normalized)
        except Exception:
            pass
        return self.read_profile(normalized)

    def merge_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        profile = self.read_profile(user_id)
        merged = _deep_merge(profile, patch)
        return self.write_profile(user_id, merged)

    def read_summary(self, user_id: str) -> str:
        normalized = _normalize_user_id(user_id)
        self._ensure_seed_state(normalized)
        return self._read_summary_raw(normalized)

    def write_summary(self, user_id: str, summary: str) -> str:
        normalized = _normalize_user_id(user_id)
        path = self._path(normalized, "summary")
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(summary or "").strip()
        if content:
            path.write_text(content, encoding="utf-8")
        elif path.exists():
            path.unlink()
        return self.read_summary(normalized)

    def read_progress(self, user_id: str) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        self._ensure_seed_state(normalized)
        return self._read_progress_raw(normalized)

    def write_progress(self, user_id: str, progress: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        path = self._path(normalized, "progress")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _json_dump(progress)
        path.write_text(payload, encoding="utf-8")
        return self.read_progress(normalized)

    def merge_progress(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        progress = self.read_progress(user_id)
        merged = _deep_merge(progress, patch)
        return self.write_progress(user_id, merged)

    def list_memory_events(self, user_id: str, limit: int | None = 20) -> list[LearnerStateEvent]:
        normalized = _normalize_user_id(user_id)
        self._ensure_seed_state(normalized)
        path = self._path(normalized, "events")
        if not path.exists():
            return []

        events: list[LearnerStateEvent] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    data = json.loads(raw)
                    events.append(LearnerStateEvent(
                        event_id=str(data.get("event_id", "") or ""),
                        user_id=str(data.get("user_id", "") or normalized),
                        source_feature=str(data.get("source_feature", "") or ""),
                        source_id=str(data.get("source_id", "") or ""),
                        source_bot_id=(str(data.get("source_bot_id", "") or "") or None),
                        memory_kind=str(data.get("memory_kind", "") or ""),
                        payload_json=dict(data.get("payload_json") or {}),
                        dedupe_key=str(data.get("dedupe_key", "") or ""),
                        created_at=str(data.get("created_at", "") or ""),
                    ))
        except Exception:
            return []

        if limit is None or limit < 0:
            return events
        return events[-limit:]

    def append_memory_event(
        self,
        user_id: str,
        *,
        source_feature: str,
        source_id: str,
        memory_kind: str,
        payload_json: dict[str, Any],
        source_bot_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> LearnerStateEvent:
        normalized = _normalize_user_id(user_id)
        event = LearnerStateEvent(
            event_id=uuid.uuid4().hex,
            user_id=normalized,
            source_feature=str(source_feature or "").strip() or "manual",
            source_id=str(source_id or "").strip() or "unknown",
            source_bot_id=str(source_bot_id or "").strip() or None,
            memory_kind=str(memory_kind or "").strip() or "manual",
            payload_json=dict(payload_json or {}),
            dedupe_key=dedupe_key or self._default_dedupe_key(
                normalized,
                source_feature=source_feature,
                source_id=source_id,
                memory_kind=memory_kind,
                payload_json=payload_json,
            ),
            created_at=_iso_now(),
        )

        path = self._path(normalized, "events")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self._event_dedupe_exists(path, event.dedupe_key):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(_json_dump(self._event_to_dict(event)) + "\n")
        self._outbox_service.enqueue(
            id=event.event_id,
            user_id=event.user_id,
            event_type=event.memory_kind,
            payload_json={
                "event_id": event.event_id,
                "source_feature": event.source_feature,
                "source_id": event.source_id,
                "source_bot_id": event.source_bot_id,
                "memory_kind": event.memory_kind,
                "payload_json": event.payload_json,
                "created_at": event.created_at,
            },
            dedupe_key=event.dedupe_key,
            created_at=event.created_at,
        )
        return event

    def record_turn_event(
        self,
        *,
        user_id: str,
        session_id: str,
        capability: str,
        user_message: str,
        assistant_message: str,
        source_bot_id: str | None = None,
        timestamp: str = "",
    ) -> LearnerStateEvent:
        return self.append_memory_event(
            user_id,
            source_feature="turn",
            source_id=session_id or timestamp or "turn",
            source_bot_id=source_bot_id,
            memory_kind="turn",
            payload_json={
                "session_id": session_id,
                "capability": capability or "chat",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "timestamp": timestamp or _iso_now(),
            },
        )

    def record_guide_event(
        self,
        *,
        user_id: str,
        guide_id: str,
        memory_kind: str,
        payload_json: dict[str, Any],
        source_bot_id: str | None = None,
    ) -> LearnerStateEvent:
        return self.append_memory_event(
            user_id,
            source_feature="guide",
            source_id=guide_id or "guide",
            source_bot_id=source_bot_id,
            memory_kind=memory_kind,
            payload_json=payload_json,
        )

    def record_notebook_event(
        self,
        *,
        user_id: str,
        notebook_id: str,
        memory_kind: str,
        payload_json: dict[str, Any],
        source_bot_id: str | None = None,
    ) -> LearnerStateEvent:
        return self.append_memory_event(
            user_id,
            source_feature="notebook",
            source_id=notebook_id or "notebook",
            source_bot_id=source_bot_id,
            memory_kind=memory_kind,
            payload_json=payload_json,
        )

    def record_progress_event(
        self,
        *,
        user_id: str,
        source_id: str,
        payload_json: dict[str, Any],
        source_feature: str = "progress",
        source_bot_id: str | None = None,
    ) -> LearnerStateEvent:
        return self.append_memory_event(
            user_id,
            source_feature=source_feature,
            source_id=source_id or "progress",
            source_bot_id=source_bot_id,
            memory_kind="progress",
            payload_json=payload_json,
        )

    def read_learning_plan(self, user_id: str, plan_id: str) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        plan = self._learning_plan_service.read_plan(plan_id)
        if not plan or plan.get("user_id") != normalized:
            return {}
        return plan

    def read_learning_plan_pages(self, user_id: str, plan_id: str) -> dict[str, Any]:
        normalized = _normalize_user_id(user_id)
        view = self._learning_plan_service.read_guided_session_view(plan_id)
        if not view or view.get("user_id") != normalized:
            return {}
        return {
            "plan_id": str(plan_id),
            "user_id": normalized,
            "source_bot_id": view.get("source_bot_id", ""),
            "pages": [
                {
                    "plan_id": str(plan_id),
                    "page_index": int(page.get("page_index", 0) or 0),
                    "page_status": str(page.get("page_status", "") or "pending"),
                    "html_content": str(page.get("html", "") or ""),
                    "error_message": str(page.get("page_error", "") or ""),
                    "generated_at": _timestamp_to_iso(page.get("updated_at")),
                }
                for page in list(view.get("pages") or [])
                if isinstance(page, dict)
            ],
        }

    async def upsert_learning_plan(
        self,
        *,
        user_id: str,
        plan_id: str,
        knowledge_points_json: list[dict[str, Any]] | None = None,
        source_material_refs_json: list[dict[str, Any]] | None = None,
        source_bot_id: str | None = None,
        status: str = "initialized",
        current_index: int = -1,
        completion_summary_md: str = "",
    ) -> LearningPlanRecord:
        normalized = _normalize_user_id(user_id)
        normalized_plan_id = _normalize_user_id(plan_id)
        async with self._safe_lock(normalized):
            existing = self._learning_plan_service.read_guided_session_view(normalized_plan_id)
            existing_pages = list(existing.get("pages") or []) if existing else []
            normalized_points = self._normalize_json_list(
                knowledge_points_json
                if knowledge_points_json is not None
                else [page for page in existing_pages]
            )
            source_refs = self._normalize_json_list(
                source_material_refs_json
                if source_material_refs_json is not None
                else (existing.get("source_material_refs_json") if existing else [])
            )
            pages = _build_learning_plan_pages(normalized_plan_id, normalized_points, existing_pages)
            plan_fields = {
                "user_id": normalized,
                "source_bot_id": str(source_bot_id or (existing or {}).get("source_bot_id") or "").strip(),
                "source_material_refs_json": source_refs,
                "status": str(status or (existing or {}).get("status") or "initialized"),
                "current_index": int(current_index),
                "summary": str(completion_summary_md or "").strip(),
                "notebook_id": str((existing or {}).get("notebook_id") or "").strip(),
                "notebook_name": str((existing or {}).get("notebook_name") or "").strip(),
                "notebook_context": str((existing or {}).get("notebook_context") or "").strip(),
                "chat_history": list((existing or {}).get("chat_history") or []),
            }
            if existing is None:
                plan = self._learning_plan_service.create_plan(
                    session_id=normalized_plan_id,
                    pages=pages,
                    **plan_fields,
                )
            else:
                plan = self._learning_plan_service.update_plan(normalized_plan_id, **plan_fields) or {}
                for page in pages:
                    page_index_value = int(page.get("page_index", 0) or 0)
                    page_fields = {
                        key: value
                        for key, value in page.items()
                        if key not in {"session_id", "page_index"}
                    }
                    self._learning_plan_service.upsert_page(
                        normalized_plan_id,
                        page_index_value,
                        **page_fields,
                    )
                plan = self._learning_plan_service.read_plan(normalized_plan_id) or plan

            return LearningPlanRecord(
                plan_id=normalized_plan_id,
                user_id=normalized,
                source_bot_id=str(plan.get("source_bot_id", "") or "").strip() or None,
                source_material_refs_json=self._normalize_json_list(plan.get("source_material_refs_json")),
                knowledge_points_json=[
                    {
                        "knowledge_title": str(page.get("knowledge_title", "") or "").strip(),
                        "knowledge_summary": str(page.get("knowledge_summary", "") or "").strip(),
                        "user_difficulty": str(page.get("user_difficulty", "") or "").strip(),
                    }
                    for page in pages
                ],
                status=str(plan.get("status", "initialized") or "initialized"),
                current_index=int(plan.get("current_index", -1) or -1),
                completion_summary_md=str(plan.get("summary", "") or "").strip(),
                created_at=_timestamp_to_iso(plan.get("created_at")) or _iso_now(),
                updated_at=_timestamp_to_iso(plan.get("updated_at")) or _iso_now(),
            )

    async def update_learning_plan_page(
        self,
        *,
        user_id: str,
        plan_id: str,
        page_index: int,
        page_status: str,
        html_content: str = "",
        error_message: str = "",
        generated_at: str | None = None,
        source_bot_id: str | None = None,
    ) -> LearningPlanPageRecord:
        normalized = _normalize_user_id(user_id)
        normalized_plan_id = _normalize_user_id(plan_id)
        async with self._safe_lock(normalized):
            existing = self._learning_plan_service.read_guided_session_view(normalized_plan_id)
            if existing is None or existing.get("user_id") != normalized:
                raise KeyError(f"learning plan not found: {normalized_plan_id}")

            page = self._learning_plan_service.upsert_page(
                normalized_plan_id,
                int(page_index),
                page_status=page_status,
                html=html_content,
                page_error=error_message,
            )
            plan_source_bot_id = str(source_bot_id or existing.get("source_bot_id") or "").strip()
            self._learning_plan_service.update_plan(
                normalized_plan_id,
                user_id=normalized,
                source_bot_id=plan_source_bot_id,
            )
            return LearningPlanPageRecord(
                plan_id=normalized_plan_id,
                page_index=int(page.get("page_index", page_index) or page_index),
                page_status=str(page.get("page_status", page_status) or page_status),
                html_content=str(page.get("html", html_content) or html_content),
                error_message=str(page.get("page_error", error_message) or error_message),
                generated_at=_timestamp_to_iso(page.get("updated_at") or generated_at) or _iso_now(),
            )

    def ensure_default_job(self, user_id: str, **kwargs: Any) -> LearnerHeartbeatJob:
        normalized = _normalize_user_id(user_id)
        profile = self._read_profile_raw(normalized)
        bot_id = str(kwargs.get("bot_id") or CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]).strip()
        channel = str(kwargs.get("channel") or "heartbeat").strip() or "heartbeat"
        policy_json = _deep_merge(
            _default_heartbeat_policy(profile, bot_id=bot_id, channel=channel),
            dict(kwargs.get("policy_json") or {}),
        )
        next_run_at = kwargs.get("next_run_at") or _default_next_heartbeat_run()
        return self._heartbeat_job_service.upsert_job(
            user_id=normalized,
            bot_id=bot_id,
            channel=channel,
            policy_json=policy_json,
            next_run_at=next_run_at,
        )

    def get_due_jobs(self, **kwargs: Any) -> list[LearnerHeartbeatJob]:
        user_id = kwargs.get("user_id")
        now = kwargs.get("now")
        jobs = self._heartbeat_job_service.list_due_jobs(now=now)
        filtered = [
            job
            for job in jobs
            if bool(job.policy_json.get("enabled", True)) and bool(job.policy_json.get("consent", False))
        ]
        if not user_id:
            return filtered
        normalized = _normalize_user_id(str(user_id))
        return [job for job in filtered if job.user_id == normalized]

    def record_run_result(self, **kwargs: Any) -> LearnerHeartbeatJob:
        job_id = str(kwargs.get("job_id") or "").strip()
        if not job_id:
            raise ValueError("job_id is required")
        success = bool(kwargs.get("success", True))
        result_json = dict(kwargs.get("result_json") or {})
        finished_at = kwargs.get("finished_at")
        next_run_at = kwargs.get("next_run_at") or _default_next_heartbeat_run(reference=finished_at)
        failure_count = 0 if success else int(kwargs.get("failure_count", 0) or 0) + 1
        job = self._heartbeat_job_service.mark_run(
            job_id=job_id,
            last_run_at=finished_at,
            next_run_at=next_run_at,
            last_result_json={**result_json, "success": success},
            failure_count=failure_count,
            status=str(kwargs.get("status") or "active"),
        )
        if job is None:
            raise KeyError(f"heartbeat job not found: {job_id}")
        return job

    async def record_guide_completion(
        self,
        *,
        user_id: str,
        guide_id: str,
        notebook_name: str,
        summary: str,
        knowledge_points: list[dict[str, Any]] | None = None,
        source_bot_id: str | None = None,
    ) -> LearnerStateEvent:
        normalized = _normalize_user_id(user_id)
        async with self._safe_lock(normalized):
            return self.record_guide_event(
                user_id=normalized,
                guide_id=guide_id,
                source_bot_id=source_bot_id,
                memory_kind="guide_completion",
                payload_json={
                    "guide_id": guide_id,
                    "notebook_name": notebook_name,
                    "summary": str(summary or "").strip(),
                    "total_points": len(knowledge_points or []),
                    "knowledge_points": [
                        {
                            "knowledge_title": str(point.get("knowledge_title", "") or "").strip(),
                            "knowledge_summary": str(point.get("knowledge_summary", "") or "").strip(),
                            "user_difficulty": str(point.get("user_difficulty", "") or "").strip(),
                        }
                        for point in (knowledge_points or [])
                        if isinstance(point, dict)
                    ],
                },
            )

    async def record_notebook_writeback(
        self,
        *,
        user_id: str,
        notebook_id: str,
        record_id: str,
        operation: str,
        title: str,
        summary: str,
        user_query: str,
        record_type: str,
        kb_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_bot_id: str | None = None,
    ) -> LearnerStateEvent:
        normalized = _normalize_user_id(user_id)
        async with self._safe_lock(normalized):
            return self.record_notebook_event(
                user_id=normalized,
                notebook_id=notebook_id,
                source_bot_id=source_bot_id,
                memory_kind=f"notebook_{operation}",
                payload_json={
                    "notebook_id": notebook_id,
                    "record_id": record_id,
                    "operation": operation,
                    "record_type": record_type,
                    "title": title,
                    "summary": summary,
                    "user_query": user_query,
                    "kb_name": kb_name,
                    "metadata": dict(metadata or {}),
                },
            )

    def read_snapshot(self, user_id: str, *, event_limit: int = 5) -> LearnerStateSnapshot:
        normalized = _normalize_user_id(user_id)
        self._ensure_seed_state(normalized)
        return LearnerStateSnapshot(
            user_id=normalized,
            profile=self.read_profile(normalized),
            summary=self.read_summary(normalized),
            progress=self.read_progress(normalized),
            memory_events=self.list_memory_events(normalized, limit=event_limit),
            profile_updated_at=self._file_updated_at(normalized, "profile"),
            summary_updated_at=self._file_updated_at(normalized, "summary"),
            progress_updated_at=self._file_updated_at(normalized, "progress"),
            memory_events_updated_at=self._file_updated_at(normalized, "events"),
        )

    def build_context(
        self,
        user_id: str,
        *,
        language: str = "zh",
        max_chars: int = 5000,
    ) -> str:
        snapshot = self.read_snapshot(user_id)
        parts: list[str] = []

        profile_text = self.render_profile_markdown(snapshot.profile, language=language)
        if profile_text:
            parts.append(f"### Student Profile\n{profile_text}")

        summary_text = snapshot.summary.strip()
        if summary_text:
            parts.append(f"### Learner Summary\n{summary_text}")

        progress_text = self.render_progress_markdown(snapshot.progress, language=language)
        if progress_text:
            parts.append(f"### Learner Progress\n{progress_text}")

        events_text = self.render_events_markdown(snapshot.memory_events, language=language)
        if events_text:
            parts.append(f"### Recent Memory Events\n{events_text}")

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars].rstrip() + "\n...[truncated]"

        if str(language).lower().startswith("zh"):
            return (
                "## 学员级长期状态\n"
                "以下内容属于当前学员的长期状态真相，按需使用，不要外溢到其他学员。\n\n"
                f"{combined}"
            )
        return (
            "## Learner State\n"
            "This is the authoritative long-term state for the current learner only.\n\n"
            f"{combined}"
        )

    async def refresh_from_turn(
        self,
        *,
        user_id: str,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "",
        language: str = "zh",
        timestamp: str = "",
        source_bot_id: str | None = None,
    ) -> LearnerStateUpdateResult:
        normalized = _normalize_user_id(user_id)
        if not user_message.strip() or not assistant_message.strip():
            summary = self.read_summary(normalized)
            return LearnerStateUpdateResult(
                content=summary,
                changed=False,
                updated_at=self._latest_updated_at(normalized),
            )
        if _should_skip_turn_writeback(
            user_message=user_message,
            assistant_message=assistant_message,
            capability=capability,
        ):
            summary = self.read_summary(normalized)
            return LearnerStateUpdateResult(
                content=summary,
                changed=False,
                updated_at=self._latest_updated_at(normalized),
            )

        async with self._safe_lock(normalized):
            self._ensure_seed_state(normalized)
            snapshot = self.read_snapshot(normalized)
            event = self.record_turn_event(
                user_id=normalized,
                session_id=session_id,
                capability=capability or "chat",
                user_message=user_message.strip(),
                assistant_message=assistant_message.strip(),
                source_bot_id=source_bot_id,
                timestamp=timestamp,
            )
            source = (
                f"[User Profile]\n{_json_dump(snapshot.profile)}\n\n"
                f"[Learner Summary]\n{snapshot.summary or '(empty)'}\n\n"
                f"[Learner Progress]\n{_json_dump(snapshot.progress)}\n\n"
                f"[Session] {session_id or '(unknown)'}\n"
                f"[Capability] {capability or 'chat'}\n"
                f"[Timestamp] {timestamp or _iso_now()}\n\n"
                f"[User]\n{user_message.strip()}\n\n"
                f"[Assistant]\n{assistant_message.strip()}"
            )
            summary_changed = await self._rewrite_summary(normalized, source, language)
            updated = self.read_snapshot(normalized)
            if summary_changed and updated.summary.strip():
                self._enqueue_summary_refresh(
                    user_id=normalized,
                    summary_md=updated.summary,
                    source_feature=capability or "chat",
                    source_id=session_id or event.event_id,
                    source_bot_id=source_bot_id,
                )
            return LearnerStateUpdateResult(
                content=updated.summary,
                changed=summary_changed or bool(event.event_id),
                updated_at=self._latest_updated_at(normalized),
            )

    async def _rewrite_summary(self, user_id: str, source: str, language: str) -> bool:
        current = self.read_summary(user_id)
        zh = str(language).lower().startswith("zh")
        sys_prompt, user_prompt = self._summary_prompts(current, source, zh)

        stream_fn = llm_stream
        if stream_fn is None:
            from deeptutor.services.llm import stream as stream_fn  # type: ignore[no-redef]

        chunks: list[str] = []
        async for chunk in stream_fn(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
            max_tokens=900,
        ):
            chunks.append(chunk)

        rewritten = _strip_code_fence("".join(chunks)).strip()
        if not rewritten or rewritten == _NO_CHANGE or rewritten == current:
            return False

        self.write_summary(user_id, rewritten)
        return True

    def _latest_updated_at(self, user_id: str) -> str | None:
        values = [
            self._file_updated_at(user_id, "profile"),
            self._file_updated_at(user_id, "summary"),
            self._file_updated_at(user_id, "progress"),
            self._file_updated_at(user_id, "events"),
        ]
        parsed = [v for v in values if v]
        if not parsed:
            return None
        return max(parsed)

    def _event_dedupe_exists(self, path: Path, dedupe_key: str) -> bool:
        if not path.exists():
            return False
        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    if not raw.strip():
                        continue
                    data = json.loads(raw)
                    if str(data.get("dedupe_key", "") or "") == dedupe_key:
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _event_to_dict(event: LearnerStateEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "user_id": event.user_id,
            "source_feature": event.source_feature,
            "source_id": event.source_id,
            "source_bot_id": event.source_bot_id,
            "memory_kind": event.memory_kind,
            "payload_json": event.payload_json,
            "dedupe_key": event.dedupe_key,
            "created_at": event.created_at,
        }

    @staticmethod
    def _default_dedupe_key(
        user_id: str,
        *,
        source_feature: str,
        source_id: str,
        memory_kind: str,
        payload_json: dict[str, Any],
    ) -> str:
        raw = _json_dump(
            {
                "user_id": user_id,
                "source_feature": source_feature,
                "source_id": source_id,
                "memory_kind": memory_kind,
                "payload_json": payload_json,
            }
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _learning_plan_to_dict(plan: LearningPlanRecord) -> dict[str, Any]:
        return {
            "plan_id": plan.plan_id,
            "user_id": plan.user_id,
            "source_bot_id": plan.source_bot_id,
            "source_material_refs_json": plan.source_material_refs_json,
            "knowledge_points_json": plan.knowledge_points_json,
            "status": plan.status,
            "current_index": plan.current_index,
            "completion_summary_md": plan.completion_summary_md,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    @staticmethod
    def _learning_plan_page_to_dict(page: LearningPlanPageRecord) -> dict[str, Any]:
        return {
            "plan_id": page.plan_id,
            "page_index": page.page_index,
            "page_status": page.page_status,
            "html_content": page.html_content,
            "error_message": page.error_message,
            "generated_at": page.generated_at,
        }

    @staticmethod
    def _empty_learning_plan_page(page_index: int) -> dict[str, Any]:
        return {
            "page_index": page_index,
            "page_status": "pending",
            "html_content": "",
            "error_message": "",
            "generated_at": None,
        }

    @staticmethod
    def _coerce_learning_plan_page(
        existing: dict[str, Any],
        *,
        plan_id: str,
        page_index: int,
        page_status: str,
        html_content: str = "",
        error_message: str = "",
        generated_at: str | None = None,
    ) -> LearningPlanPageRecord:
        return LearningPlanPageRecord(
            plan_id=plan_id,
            page_index=page_index,
            page_status=str(page_status or existing.get("page_status") or "pending"),
            html_content=str(html_content if html_content is not None else existing.get("html_content", "")).strip(),
            error_message=str(error_message if error_message is not None else existing.get("error_message", "")).strip(),
            generated_at=generated_at if generated_at is not None else existing.get("generated_at") or None,
        )

    @staticmethod
    def _normalize_json_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8").strip()
            return dict(json.loads(content)) if content else {}
        except Exception:
            return {}

    def _read_learning_plan_pages_raw(self, user_id: str, plan_id: str) -> dict[str, Any]:
        return self._read_json_file(self._learning_plan_pages_path(user_id, plan_id))

    @staticmethod
    def _merge_learning_plan_pages(
        plan_id: str,
        knowledge_points: list[dict[str, Any]],
        existing_pages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        total_pages = max(len(knowledge_points), len(existing_pages))
        pages: list[dict[str, Any]] = []
        for page_index in range(total_pages):
            existing = (
                existing_pages[page_index]
                if page_index < len(existing_pages) and isinstance(existing_pages[page_index], dict)
                else {}
            )
            page = LearningPlanPageRecord(
                plan_id=plan_id,
                page_index=page_index,
                page_status=str(existing.get("page_status") or "pending"),
                html_content=str(existing.get("html_content") or "").strip(),
                error_message=str(existing.get("error_message") or "").strip(),
                generated_at=existing.get("generated_at") or None,
            )
            pages.append(LearnerStateService._learning_plan_page_to_dict(page))
        return pages

    @staticmethod
    def render_profile_markdown(profile: dict[str, Any], *, language: str = "zh") -> str:
        display_name = _preferred_display_name(profile)
        nickname_status = "已确认专属称呼" if _has_stable_display_name(profile) else "称呼待进一步确认"
        urgency = _exam_urgency_hint(profile.get("exam_date"))
        level_hint = _level_hint(profile.get("level"))
        lines = [
            "## 学员识别" if str(language).lower().startswith("zh") else "## Learner Identity",
            f"- 学员ID：{_display(profile.get('user_id'))}" if str(language).lower().startswith("zh") else f"- Learner ID: {_display(profile.get('user_id'))}",
            f"- 当前称呼：{display_name}" if str(language).lower().startswith("zh") else f"- Display name: {display_name}",
            f"- 称呼状态：{nickname_status}" if str(language).lower().startswith("zh") else f"- Naming status: {nickname_status}",
            (
                f"- 称呼使用建议：回答开头可自然称呼“{display_name}”，但不要在每段重复称呼。"
                if str(language).lower().startswith("zh")
                else f"- Naming guidance: you may use “{display_name}” naturally, but avoid repeating it in every paragraph."
            )
            if _has_stable_display_name(profile)
            else (
                "- 称呼使用建议：当前先用自然中性称呼；若合适，后续可确认用户更希望被怎么称呼。"
                if str(language).lower().startswith("zh")
                else "- Naming guidance: use a neutral greeting for now and confirm the preferred name later if appropriate."
            ),
            "",
            "## 备考主线" if str(language).lower().startswith("zh") else "## Study Focus",
            f"- 默认场景：建筑工程类考试与《建筑工程管理与实务》学习" if str(language).lower().startswith("zh") else "- Default context: construction exam preparation and practice learning",
            f"- 会员等级：{_display(profile.get('tier'))}" if str(language).lower().startswith("zh") else f"- Membership tier: {_display(profile.get('tier'))}",
            f"- 账号状态：{_display(profile.get('status'))}" if str(language).lower().startswith("zh") else f"- Account status: {_display(profile.get('status'))}",
            f"- 考试日期：{_display(profile.get('exam_date'))}" if str(language).lower().startswith("zh") else f"- Exam date: {_display(profile.get('exam_date'))}",
            f"- 备考紧迫度：{urgency}" if str(language).lower().startswith("zh") else f"- Urgency: {urgency}",
            f"- 当前聚焦：{_display(profile.get('focus_topic'))}" if str(language).lower().startswith("zh") else f"- Focus topic: {_display(profile.get('focus_topic'))}",
            f"- 当前目标提问：{_display(profile.get('focus_query'))}" if str(language).lower().startswith("zh") else f"- Focus query: {_display(profile.get('focus_query'))}",
            "",
            "## 学习偏好" if str(language).lower().startswith("zh") else "## Learning Preferences",
            f"- 难度偏好：{_difficulty_label(profile.get('difficulty_preference'))}" if str(language).lower().startswith("zh") else f"- Difficulty preference: {_difficulty_label(profile.get('difficulty_preference'))}",
            f"- 讲解风格：{_explanation_style_label(profile.get('explanation_style'))}" if str(language).lower().startswith("zh") else f"- Explanation style: {_explanation_style_label(profile.get('explanation_style'))}",
            f"- 每日目标：{_display(profile.get('daily_target'), suffix='题/次')}" if str(language).lower().startswith("zh") else f"- Daily target: {_display(profile.get('daily_target'))}",
            f"- 复习提醒：{_display_bool(profile.get('review_reminder'))}" if str(language).lower().startswith("zh") else f"- Review reminder: {_display_bool(profile.get('review_reminder'))}",
            "",
            "## 当前学习判断" if str(language).lower().startswith("zh") else "## Learning Snapshot",
            f"- 当前等级：{_display(profile.get('level'))}" if str(language).lower().startswith("zh") else f"- Current level: {_display(profile.get('level'))}",
            f"- 基础判断：{level_hint}" if str(language).lower().startswith("zh") else f"- Level hint: {level_hint}",
            f"- 积分余额：{_display(profile.get('points'))}" if str(language).lower().startswith("zh") else f"- Points balance: {_display(profile.get('points'))}",
            (
                "- 当前支持重点：先稳住节奏，再围绕当前聚焦专题持续推进。"
                if str(language).lower().startswith("zh")
                else "- Support focus: keep the pace steady and keep moving on the current focus topic."
            )
            if str(profile.get("focus_topic") or "").strip()
            else (
                "- 当前支持重点：先帮助学员确认最近最值得投入的一个专题。"
                if str(language).lower().startswith("zh")
                else "- Support focus: first identify the most valuable topic to invest in next."
            ),
        ]
        return "\n".join(lines).strip()

    @staticmethod
    def render_progress_markdown(progress: dict[str, Any], *, language: str = "zh") -> str:
        if not progress:
            return ""
        today = dict(progress.get("today") or {})
        chapters = list(progress.get("chapters") or [])
        lines: list[str] = []
        if today:
            lines.append("## 今日进度" if str(language).lower().startswith("zh") else "## Today")
            if str(language).lower().startswith("zh"):
                lines.append(f"- 今日完成：{_display(today.get('today_done'))}")
                lines.append(f"- 每日目标：{_display(today.get('daily_target'))}")
                lines.append(f"- 连续天数：{_display(today.get('streak_days'))}")
            else:
                lines.append(f"- Done today: {_display(today.get('today_done'))}")
                lines.append(f"- Daily target: {_display(today.get('daily_target'))}")
                lines.append(f"- Streak days: {_display(today.get('streak_days'))}")
        if chapters:
            if lines:
                lines.append("")
            lines.append("## 专题进度" if str(language).lower().startswith("zh") else "## Chapter Progress")
            for item in chapters[:8]:
                name = _display(item.get("chapter_name"), fallback=str(item.get("chapter_id") or ""))
                done = _display(item.get("done"))
                total = _display(item.get("total"))
                lines.append(
                    f"- {name}：{done}/{total}" if str(language).lower().startswith("zh") else f"- {name}: {done}/{total}"
                )
        return "\n".join(lines).strip()

    @staticmethod
    def render_events_markdown(events: list[LearnerStateEvent], *, language: str = "zh") -> str:
        if not events:
            return ""
        lines = [
            "## 最近事件" if str(language).lower().startswith("zh") else "## Recent Events",
        ]
        for event in events[-5:]:
            kind = event.memory_kind or "manual"
            source = event.source_feature or "unknown"
            source_id = event.source_id or "unknown"
            lines.append(
                (
                    f"- {kind} / {source} / {source_id}"
                    if str(language).lower().startswith("zh")
                    else f"- {kind} / {source} / {source_id}"
                )
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _seed_progress(
        profile: dict[str, Any],
        user_id: str,
        member_progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        member_progress = dict(member_progress or {})
        today = dict(member_progress.get("today") or {})
        chapters = list(member_progress.get("chapters") or [])
        return {
            "user_id": user_id,
            "today": {
                "today_done": today.get("today_done", 0),
                "daily_target": today.get("daily_target", profile.get("daily_target", 0)),
                "streak_days": today.get("streak_days", 0),
            },
            "chapters": chapters,
        }

    @staticmethod
    def _seed_summary(profile: dict[str, Any], progress: dict[str, Any]) -> str:
        focus_topic = _display(profile.get("focus_topic"), fallback="待确认")
        today = dict(progress.get("today") or {})
        return "\n".join(
            [
                "## 当前学习概览",
                f"- 当前聚焦：{focus_topic}",
                f"- 今日完成：{_display(today.get('today_done'))}",
                f"- 每日目标：{_display(today.get('daily_target'))}",
                "",
                "## 稳定偏好",
                f"- 难度：{_display(profile.get('difficulty_preference'))}",
                f"- 讲解方式：{_display(profile.get('explanation_style'))}",
                "",
                "## 待持续观察",
                "- 常错点、易混点、已经掌握的题型、下次建议跟进的练习。",
            ]
        ).strip()

    @staticmethod
    def _summary_prompts(current: str, source: str, zh: bool) -> tuple[str, str]:
        if zh:
            return (
                "你负责维护当前学员的长期学习摘要。"
                "只保留跨回合仍有价值的学习状态、稳定偏好、典型误区、进展和下一次跟进建议。"
                f"如果无需修改，请只返回 {_NO_CHANGE}。",
                "如果需要更新，请重写长期学习摘要，可使用以下标题：\n"
                "## 当前学习概览\n## 稳定偏好\n## 待持续观察\n## 下一步建议\n\n"
                "规则：保持简短；删除寒暄、一次性回答和过时信息；不要泄露其他学员信息。\n\n"
                f"[当前长期摘要]\n{current or '(empty)'}\n\n"
                f"[新增材料]\n{source}",
            )
        return (
            "You maintain the learner's long-term study summary. "
            "Keep only durable learning state, stable preferences, misconceptions, progress, "
            f"and the next useful follow-up. If nothing should change, return exactly {_NO_CHANGE}.",
            "Rewrite the long-term learning summary if needed. Suggested sections:\n"
            "## Current Learning Overview\n## Stable Preferences\n## Watch Items\n## Next Step\n\n"
            "Rules: keep it short, remove stale or transient chatter, never mix other learners.\n\n"
            f"[Current summary]\n{current or '(empty)'}\n\n"
            f"[New material]\n{source}",
        )


_learner_state_service: LearnerStateService | None = None


def get_learner_state_service() -> LearnerStateService:
    global _learner_state_service
    if _learner_state_service is None:
        _learner_state_service = LearnerStateService()
    return _learner_state_service


def _normalize_user_id(user_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(user_id or "").strip())
    if not cleaned:
        raise ValueError("user_id is required")
    return cleaned[:120]


def _should_skip_turn_writeback(
    *,
    user_message: str,
    assistant_message: str,
    capability: str,
) -> bool:
    normalized_capability = str(capability or "").strip().lower()
    if normalized_capability.startswith("guide") or normalized_capability.startswith("notebook"):
        return False

    text = re.sub(r"\s+", "", str(user_message or "").strip().lower())
    if not text:
        return True
    if len(text) <= 12 and text in _LOW_SIGNAL_TURN_PATTERNS:
        return True
    if any(token in text for token in _NON_LEARNING_ACCOUNT_HINTS) and not any(
        token in text for token in _LEARNING_HINTS
    ):
        return True
    assistant_text = str(assistant_message or "").strip()
    return len(text) <= 8 and len(assistant_text) <= 80


def _strip_code_fence(content: str) -> str:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _display(value: Any, *, fallback: str = "未设置", suffix: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return f"{text}{suffix}" if suffix else text


def _display_bool(value: Any) -> str:
    return "开启" if bool(value) else "关闭"


def _preferred_display_name(profile: dict[str, Any]) -> str:
    display_name = str(profile.get("display_name") or profile.get("username") or "").strip()
    if display_name:
        return display_name
    return "这位学员"


def _has_stable_display_name(profile: dict[str, Any]) -> bool:
    display_name = str(profile.get("display_name") or profile.get("username") or "").strip()
    user_id = str(profile.get("user_id") or "").strip()
    if not display_name:
        return False
    generic_prefixes = ("用户", "学员", "微信用户")
    if user_id and display_name == user_id:
        return False
    if display_name in {"用户", "同学", "学员"}:
        return False
    return not any(display_name.startswith(prefix) and len(display_name) <= 8 for prefix in generic_prefixes)


def _difficulty_label(value: Any) -> str:
    mapping = {
        "easy": "简单，先求做对与建立信心",
        "medium": "适中，兼顾做对与理解",
        "hard": "挑战，允许更强推理与迁移",
    }
    key = str(value or "").strip().lower()
    return mapping.get(key, _display(value))


def _explanation_style_label(value: Any) -> str:
    mapping = {
        "brief": "简洁，先给抓手和结论",
        "detailed": "详细，把逻辑讲透",
        "socratic": "启发式，引导学员自己推出关键判断",
    }
    key = str(value or "").strip().lower()
    return mapping.get(key, _display(value))


def _level_hint(value: Any) -> str:
    try:
        level = int(value or 0)
    except (TypeError, ValueError):
        return "基础待进一步观察"
    if level <= 3:
        return "基础偏弱，先稳住做题正确率与核心判断框架"
    if level <= 6:
        return "基础中等，重点补齐易错点并建立同类题迁移"
    if level <= 8:
        return "基础较好，可以在做对基础上强化案例题表达与综合判断"
    return "基础较强，可适当提高综合题与变式题训练强度"


def _exam_urgency_hint(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "考试时间未明确，默认按稳步推进处理"
    try:
        exam_date = datetime.fromisoformat(text).date()
    except ValueError:
        return "考试时间已设置，建议结合日期动态安排节奏"
    today = datetime.now().date()
    days = (exam_date - today).days
    if days < 0:
        return "考试日期已过，建议先确认新的备考节点"
    if days <= 30:
        return "考前冲刺期，优先稳住高频考点、案例题与错题复盘"
    if days <= 90:
        return "中短期备考期，重点建立专题框架并提高做题稳定性"
    return "长期备考期，可系统推进知识框架与专题训练"


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _timestamp_to_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone().isoformat()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).astimezone().isoformat()
    except ValueError:
        return None


def _build_learning_plan_pages(
    plan_id: str,
    knowledge_points: list[dict[str, Any]],
    existing_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    total_pages = max(len(knowledge_points), len(existing_pages))
    for page_index in range(total_pages):
        knowledge = knowledge_points[page_index] if page_index < len(knowledge_points) else {}
        existing = existing_pages[page_index] if page_index < len(existing_pages) else {}
        pages.append(
            {
                "session_id": plan_id,
                "page_index": page_index,
                "knowledge_title": str(knowledge.get("knowledge_title") or existing.get("knowledge_title") or "").strip(),
                "knowledge_summary": str(
                    knowledge.get("knowledge_summary") or existing.get("knowledge_summary") or ""
                ).strip(),
                "user_difficulty": str(
                    knowledge.get("user_difficulty") or existing.get("user_difficulty") or ""
                ).strip(),
                "html": str(existing.get("html") or "").strip(),
                "page_status": str(existing.get("page_status") or "pending").strip() or "pending",
                "page_error": str(existing.get("page_error") or "").strip(),
            }
        )
    return pages


def _default_heartbeat_policy(
    profile: dict[str, Any],
    *,
    bot_id: str,
    channel: str,
) -> dict[str, Any]:
    heartbeat_preferences = dict(profile.get("heartbeat_preferences") or {})
    consent = dict(profile.get("consent") or {})
    quiet_hours = heartbeat_preferences.get("quiet_hours") or ["22:00", "08:00"]
    cadence = str(heartbeat_preferences.get("cadence") or "daily").strip() or "daily"
    interval_hours = 24 if cadence not in {"hourly", "adaptive"} else 6
    return {
        "enabled": bool(heartbeat_preferences.get("enabled", True)),
        "consent": bool(consent.get("heartbeat", False)),
        "quiet_hours": quiet_hours,
        "cadence": cadence,
        "timezone": str(profile.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai",
        "bot_id": bot_id,
        "channel": channel,
        "interval_hours": int(heartbeat_preferences.get("interval_hours") or interval_hours),
    }


def _default_next_heartbeat_run(reference: Any | None = None) -> str:
    if isinstance(reference, datetime):
        base = reference
    elif reference:
        try:
            base = datetime.fromisoformat(str(reference))
        except ValueError:
            base = datetime.now(timezone.utc)
    else:
        base = datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base.astimezone() + timedelta(hours=24)).isoformat()
