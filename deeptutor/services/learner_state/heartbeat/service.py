from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.path_service import PathService, get_path_service

from .store import LearnerHeartbeatJob, LearnerHeartbeatJobStore, _coerce_datetime, new_job_id

_DEFAULT_BOT_ID = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
_DEFAULT_CHANNEL = "heartbeat"
_DEFAULT_INTERVAL_HOURS = 24
_DEFAULT_STATUS = "active"


class LearnerHeartbeatService:
    """Learner-level heartbeat job service backed by local files."""

    def __init__(
        self,
        path_service: PathService | None = None,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        default_store_path = self._path_service.project_root / "data" / "runtime" / "learner_state" / "heartbeat_jobs.json"
        self._store = LearnerHeartbeatJobStore(store_path or default_store_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc).astimezone())

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone()

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return str(value or "").strip()

    @staticmethod
    def _copy_policy(policy_json: dict[str, Any] | None) -> dict[str, Any]:
        return dict(policy_json or {})

    def upsert_job(
        self,
        *,
        user_id: str,
        bot_id: str,
        channel: str,
        policy_json: dict[str, Any] | None,
        next_run_at: datetime | str,
        job_id: str | None = None,
    ) -> LearnerHeartbeatJob:
        normalized_user_id = self._normalize_text(user_id)
        normalized_bot_id = self._normalize_text(bot_id)
        normalized_channel = self._normalize_text(channel)
        if not normalized_user_id:
            raise ValueError("user_id is required")
        if not normalized_bot_id:
            raise ValueError("bot_id is required")
        if not normalized_channel:
            raise ValueError("channel is required")

        existing = self._store.get_by_identity(normalized_user_id, normalized_bot_id, normalized_channel)
        now = self._now()
        next_run_dt = _coerce_datetime(next_run_at)
        if next_run_dt is None:
            raise ValueError("next_run_at is required")

        if existing:
            job = LearnerHeartbeatJob(
                job_id=existing.job_id,
                user_id=existing.user_id,
                bot_id=existing.bot_id,
                channel=existing.channel,
                policy_json=self._copy_policy(policy_json),
                next_run_at=next_run_dt,
                last_run_at=existing.last_run_at,
                last_result_json=existing.last_result_json,
                failure_count=existing.failure_count,
                status=existing.status,
                created_at=existing.created_at,
                updated_at=now,
            )
        else:
            job = LearnerHeartbeatJob(
                job_id=job_id or new_job_id(),
                user_id=normalized_user_id,
                bot_id=normalized_bot_id,
                channel=normalized_channel,
                policy_json=self._copy_policy(policy_json),
                next_run_at=next_run_dt,
                last_run_at=None,
                last_result_json=None,
                failure_count=0,
                status="active",
                created_at=now,
                updated_at=now,
            )

        return self._store.upsert(job)

    def pause_job(self, job_id: str) -> LearnerHeartbeatJob | None:
        return self._store.pause(self._normalize_text(job_id), self._now())

    def resume_job(self, job_id: str) -> LearnerHeartbeatJob | None:
        return self._store.resume(self._normalize_text(job_id), self._now())

    def get_job(self, job_id: str) -> LearnerHeartbeatJob | None:
        return self._store.get_by_id(self._normalize_text(job_id))

    def list_jobs(self, *, user_id: str | None = None) -> list[LearnerHeartbeatJob]:
        normalized_user_id = self._normalize_text(user_id) if user_id is not None else None
        return self._store.list_jobs(user_id=normalized_user_id or None)

    def list_due_jobs(self, now: datetime | str | None = None) -> list[LearnerHeartbeatJob]:
        current = _coerce_datetime(now) if now is not None else self._now()
        if current is None:
            current = self._now()
        return self._store.list_due_jobs(current)

    def mark_run(
        self,
        *,
        job_id: str,
        next_run_at: datetime | str | None,
        last_result_json: dict[str, Any] | None,
        failure_count: int,
        status: str = "active",
        last_run_at: datetime | str | None = None,
    ) -> LearnerHeartbeatJob | None:
        current = self._now()
        run_at = _coerce_datetime(last_run_at) if last_run_at is not None else current
        next_run_dt = _coerce_datetime(next_run_at) if next_run_at is not None else None
        normalized_status = self._normalize_text(status) or "active"
        if normalized_status not in {"active", "paused", "stopped"}:
            raise ValueError("status must be active, paused, or stopped")
        return self._store.mark_run(
            job_id=self._normalize_text(job_id),
            last_run_at=run_at or current,
            next_run_at=next_run_dt,
            last_result_json=dict(last_result_json or {}),
            failure_count=int(failure_count),
            status=normalized_status,  # type: ignore[arg-type]
            updated_at=current,
        )

    def ensure_default_job(
        self,
        user_id: str,
        *,
        bot_id: str | None = None,
        channel: str = _DEFAULT_CHANNEL,
        policy_json: dict[str, Any] | None = None,
        next_run_at: datetime | str | None = None,
        status: str | None = None,
    ) -> LearnerHeartbeatJob:
        normalized_user_id = self._normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("user_id is required")
        normalized_bot_id = self._normalize_text(bot_id) or _DEFAULT_BOT_ID
        normalized_channel = self._normalize_text(channel) or _DEFAULT_CHANNEL
        existing = self._store.get_by_identity(normalized_user_id, normalized_bot_id, normalized_channel)
        current = self._now()
        merged_policy = _deep_merge(_default_policy_json(normalized_bot_id, normalized_channel), policy_json)
        next_run_dt = _coerce_datetime(next_run_at) if next_run_at is not None else None

        if existing:
            job = LearnerHeartbeatJob(
                job_id=existing.job_id,
                user_id=existing.user_id,
                bot_id=existing.bot_id,
                channel=existing.channel,
                policy_json=_deep_merge(existing.policy_json, policy_json) if policy_json is not None else existing.policy_json,
                next_run_at=next_run_dt if next_run_dt is not None else existing.next_run_at,
                last_run_at=existing.last_run_at,
                last_result_json=existing.last_result_json,
                failure_count=existing.failure_count,
                status=self._normalize_text(status) or existing.status,
                created_at=existing.created_at,
                updated_at=current,
            )
        else:
            job = LearnerHeartbeatJob(
                job_id=new_job_id(),
                user_id=normalized_user_id,
                bot_id=normalized_bot_id,
                channel=normalized_channel,
                policy_json=merged_policy,
                next_run_at=next_run_dt or _schedule_next_run(merged_policy, current),
                last_run_at=None,
                last_result_json=None,
                failure_count=0,
                status=self._normalize_text(status) or _DEFAULT_STATUS,
                created_at=current,
                updated_at=current,
            )

        return self._store.upsert(job)

    def get_due_jobs(
        self,
        *,
        user_id: str | None = None,
        now: datetime | str | None = None,
    ) -> list[LearnerHeartbeatJob]:
        current = _coerce_datetime(now) if now is not None else self._now()
        if current is None:
            current = self._now()
        due = [
            job
            for job in self._store.list_due_jobs(current)
            if _is_heartbeat_job_enabled(job, current)
        ]
        if user_id is None:
            return due
        normalized_user_id = self._normalize_text(user_id)
        return [job for job in due if job.user_id == normalized_user_id]

    def record_run_result(
        self,
        *,
        user_id: str,
        job_id: str,
        success: bool,
        result_json: dict[str, Any] | None = None,
        finished_at: datetime | str | None = None,
        next_run_at: datetime | str | None = None,
    ) -> LearnerHeartbeatJob:
        normalized_user_id = self._normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("user_id is required")
        normalized_job_id = self._normalize_text(job_id)
        if not normalized_job_id:
            raise ValueError("job_id is required")

        store = self._store
        job = store.get_by_id(normalized_job_id)
        if job is None:
            raise KeyError(f"heartbeat job not found: {normalized_job_id}")
        if job.user_id != normalized_user_id:
            raise KeyError(f"heartbeat job user mismatch: {normalized_job_id}")

        current = self._now()
        run_at = _coerce_datetime(finished_at) if finished_at is not None else current
        next_run_dt = _coerce_datetime(next_run_at) if next_run_at is not None else None
        failure_count = 0 if success else int(job.failure_count) + 1
        status = job.status if job.status in {"active", "paused", "stopped"} else "active"
        normalized_result_json = _normalize_heartbeat_result_json(
            job=job,
            success=success,
            result_json=result_json,
            recorded_at=run_at or current,
        )

        updated = store.mark_run(
            job_id=normalized_job_id,
            last_run_at=run_at or current,
            next_run_at=next_run_dt
            or _schedule_next_run(
                job.policy_json,
                run_at or current,
                failure_count=failure_count,
                success=success,
            ),
            last_result_json=normalized_result_json,
            failure_count=failure_count,
            status=status,  # type: ignore[arg-type]
            updated_at=current,
        )
        if updated is None:
            raise KeyError(f"heartbeat job not found: {normalized_job_id}")
        return updated


def _default_policy_json(bot_id: str, channel: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "consent": False,
        "interval_hours": _DEFAULT_INTERVAL_HOURS,
        "quiet_hours": {"start": 22, "end": 8},
        "bot_id": bot_id,
        "channel": channel,
    }


def _schedule_next_run(
    policy_json: dict[str, Any] | None,
    reference_at: datetime,
    *,
    failure_count: int = 0,
    success: bool = True,
) -> datetime:
    policy = dict(policy_json or {})
    interval_hours = _DEFAULT_INTERVAL_HOURS
    raw_interval = policy.get("interval_hours")
    if raw_interval is None and policy.get("interval_minutes") is not None:
        try:
            raw_interval = max(1, int(policy.get("interval_minutes")) // 60 or 1)
        except Exception:
            raw_interval = None
    try:
        if raw_interval is not None:
            interval_hours = max(1, int(raw_interval))
    except Exception:
        interval_hours = _DEFAULT_INTERVAL_HOURS

    multiplier = 1 if success else min(2 ** max(0, failure_count - 1), 8)
    return reference_at + timedelta(hours=interval_hours * multiplier)


def _normalize_heartbeat_result_json(
    *,
    job: LearnerHeartbeatJob,
    success: bool,
    result_json: dict[str, Any] | None,
    recorded_at: datetime,
) -> dict[str, Any]:
    payload = dict(result_json or {})
    delivery = dict(payload.get("delivery") or {})
    audit = dict(payload.get("audit") or {})
    recorded_at_iso = recorded_at.isoformat()
    delivery_state = str(
        payload.get("delivery_state")
        or delivery.get("state")
        or ("sent" if success else "failed")
    ).strip() or ("sent" if success else "failed")

    delivery.setdefault("state", delivery_state)
    if "message" not in delivery and payload.get("message") is not None:
        delivery["message"] = payload.get("message")
    if "message_len" not in delivery and isinstance(delivery.get("message"), str):
        delivery["message_len"] = len(str(delivery.get("message") or ""))
    delivery.setdefault("conversation_id", f"learner-heartbeat:{job.user_id}:{job.channel}")
    delivery.setdefault("channel", job.channel)
    delivery.setdefault("bot_id", job.bot_id)
    delivery.setdefault("user_id", job.user_id)

    audit.setdefault("job_id", job.job_id)
    audit.setdefault("user_id", job.user_id)
    audit.setdefault("bot_id", job.bot_id)
    audit.setdefault("channel", job.channel)
    audit.setdefault("source", "learner_heartbeat")
    audit.setdefault("conversation_id", delivery.get("conversation_id"))
    audit["status"] = "ok" if success else "error"
    audit["success"] = bool(success)
    audit["recorded_at"] = recorded_at_iso

    normalized = {
        **payload,
        "success": bool(success),
        "recorded_at": recorded_at_iso,
        "job_id": job.job_id,
        "user_id": job.user_id,
        "bot_id": job.bot_id,
        "channel": job.channel,
        "delivery_state": delivery_state,
        "delivery": delivery,
        "audit": audit,
    }
    if not success and "error" not in normalized and payload.get("error") is not None:
        normalized["error"] = payload.get("error")
    return normalized


def _is_heartbeat_job_enabled(job: LearnerHeartbeatJob, current: datetime) -> bool:
    policy = dict(job.policy_json or {})
    if not bool(policy.get("enabled", True)):
        return False
    if not bool(policy.get("consent", False)):
        return False
    if _is_within_quiet_hours(policy, current):
        return False
    if _is_in_cooldown(job, current):
        return False
    if _is_snoozed(job, current):
        return False
    if _has_negative_feedback_stop(job):
        return False
    return True


def _is_within_quiet_hours(policy: dict[str, Any], current: datetime) -> bool:
    raw_quiet_hours = policy.get("quiet_hours")
    if not raw_quiet_hours:
        return False
    timezone_name = str(policy.get("timezone") or "UTC").strip() or "UTC"
    try:
        localized = current.astimezone(ZoneInfo(timezone_name))
    except Exception:
        localized = current
    minutes = localized.hour * 60 + localized.minute
    if isinstance(raw_quiet_hours, dict):
        start_minutes = _parse_quiet_hour_value(raw_quiet_hours.get("start"))
        end_minutes = _parse_quiet_hour_value(raw_quiet_hours.get("end"))
    elif isinstance(raw_quiet_hours, (list, tuple)) and len(raw_quiet_hours) >= 2:
        start_minutes = _parse_quiet_hour_value(raw_quiet_hours[0])
        end_minutes = _parse_quiet_hour_value(raw_quiet_hours[1])
    else:
        return False
    if start_minutes is None or end_minutes is None or start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= minutes < end_minutes
    return minutes >= start_minutes or minutes < end_minutes


def _is_in_cooldown(job: LearnerHeartbeatJob, current: datetime) -> bool:
    policy = dict(job.policy_json or {})
    try:
        cooldown_hours = max(0, int(policy.get("cooldown_hours") or 0))
    except Exception:
        cooldown_hours = 0
    if cooldown_hours <= 0 or job.last_run_at is None:
        return False
    return current < job.last_run_at + timedelta(hours=cooldown_hours)


def _is_snoozed(job: LearnerHeartbeatJob, current: datetime) -> bool:
    last_result = dict(job.last_result_json or {})
    snooze_until = _coerce_datetime(last_result.get("snooze_until"))
    return snooze_until is not None and current < snooze_until


def _has_negative_feedback_stop(job: LearnerHeartbeatJob) -> bool:
    last_result = dict(job.last_result_json or {})
    feedback_action = str(
        last_result.get("feedback_action")
        or last_result.get("negative_feedback_action")
        or ""
    ).strip().lower()
    if feedback_action in {"stop", "pause"}:
        return True
    feedback = last_result.get("negative_feedback")
    return isinstance(feedback, dict) and bool(feedback.get("stop"))


def _parse_quiet_hour_value(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, int):
        return max(0, min(23, value)) * 60
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        hours_text, minutes_text = (text.split(":", 1) + ["0"])[:2]
        try:
            hours = max(0, min(23, int(hours_text)))
            minutes = max(0, min(59, int(minutes_text)))
        except Exception:
            return None
        return hours * 60 + minutes
    try:
        return max(0, min(23, int(text))) * 60
    except Exception:
        return None


def _iter_user_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [item.name for item in sorted(root.iterdir(), key=lambda path: path.name) if item.is_dir()]


def _deep_merge(base: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    for key, value in dict(patch or {}).items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


__all__ = ["LearnerHeartbeatService"]
