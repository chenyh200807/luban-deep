from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

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
            if bool(job.policy_json.get("enabled", True)) and bool(job.policy_json.get("consent", False))
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
            last_result_json={
                **dict(result_json or {}),
                "success": bool(success),
                "recorded_at": (run_at or current).isoformat(),
            },
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
