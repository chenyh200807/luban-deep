from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        dt = datetime.fromisoformat(text)
    else:
        raise TypeError(f"unsupported datetime value: {type(value)!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _to_iso(value: datetime | None) -> str | None:
    dt = _coerce_datetime(value)
    return dt.isoformat() if dt else None


def _copy_json(value: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(value or {}, ensure_ascii=False))


@dataclass
class LearnerHeartbeatJob:
    job_id: str
    user_id: str
    bot_id: str
    channel: str
    policy_json: dict[str, Any]
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_result_json: dict[str, Any] | None
    failure_count: int
    status: Literal["active", "paused", "stopped"]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "bot_id": self.bot_id,
            "channel": self.channel,
            "policy_json": _copy_json(self.policy_json),
            "next_run_at": _to_iso(self.next_run_at),
            "last_run_at": _to_iso(self.last_run_at),
            "last_result_json": _copy_json(self.last_result_json),
            "failure_count": int(self.failure_count),
            "status": self.status,
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerHeartbeatJob":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            bot_id=str(payload.get("bot_id") or ""),
            channel=str(payload.get("channel") or ""),
            policy_json=_copy_json(payload.get("policy_json") if isinstance(payload.get("policy_json"), dict) else {}),
            next_run_at=_coerce_datetime(payload.get("next_run_at")),
            last_run_at=_coerce_datetime(payload.get("last_run_at")),
            last_result_json=(
                _copy_json(payload.get("last_result_json"))
                if isinstance(payload.get("last_result_json"), dict)
                else None
            ),
            failure_count=int(payload.get("failure_count") or 0),
            status=str(payload.get("status") or "active").strip() or "active",
            created_at=_coerce_datetime(payload.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_coerce_datetime(payload.get("updated_at")) or datetime.now(timezone.utc),
        )


class LearnerHeartbeatJobStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path

    def load(self) -> list[LearnerHeartbeatJob]:
        if not self.store_path.exists():
            return []
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        jobs: list[LearnerHeartbeatJob] = []
        for item in payload.get("jobs", []):
            if isinstance(item, dict):
                try:
                    jobs.append(LearnerHeartbeatJob.from_dict(item))
                except Exception:
                    continue
        return jobs

    def save(self, jobs: list[LearnerHeartbeatJob]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "jobs": [job.to_dict() for job in jobs],
        }
        tmp_path = self.store_path.with_suffix(f"{self.store_path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.store_path)

    def get_by_id(self, job_id: str) -> LearnerHeartbeatJob | None:
        for job in self.load():
            if job.job_id == job_id:
                return job
        return None

    def get_by_identity(self, user_id: str, bot_id: str, channel: str) -> LearnerHeartbeatJob | None:
        for job in self.load():
            if job.user_id == user_id and job.bot_id == bot_id and job.channel == channel:
                return job
        return None

    def list_jobs(self, *, user_id: str | None = None) -> list[LearnerHeartbeatJob]:
        jobs = self.load()
        if user_id is not None:
            jobs = [job for job in jobs if job.user_id == user_id]
        return sorted(
            jobs,
            key=lambda job: (
                0 if job.status == "active" else 1,
                _to_iso(job.next_run_at) or "9999-12-31T23:59:59+00:00",
                _to_iso(job.created_at) or "",
                job.job_id,
            ),
        )

    def upsert(self, job: LearnerHeartbeatJob) -> LearnerHeartbeatJob:
        jobs = self.load()
        index = next((i for i, item in enumerate(jobs) if item.job_id == job.job_id), None)
        if index is None:
            index = next(
                (
                    i
                    for i, item in enumerate(jobs)
                    if item.user_id == job.user_id and item.bot_id == job.bot_id and item.channel == job.channel
                ),
                None,
            )

        if index is None:
            jobs.append(job)
        else:
            jobs[index] = job

        self.save(jobs)
        return job

    def pause(self, job_id: str, updated_at: datetime) -> LearnerHeartbeatJob | None:
        return self._mutate(job_id, updated_at, status="paused")

    def resume(self, job_id: str, updated_at: datetime) -> LearnerHeartbeatJob | None:
        return self._mutate(job_id, updated_at, status="active")

    def mark_run(
        self,
        *,
        job_id: str,
        last_run_at: datetime,
        next_run_at: datetime | None,
        last_result_json: dict[str, Any] | None,
        failure_count: int,
        status: Literal["active", "paused", "stopped"],
        updated_at: datetime,
    ) -> LearnerHeartbeatJob | None:
        jobs = self.load()
        for index, item in enumerate(jobs):
            if item.job_id != job_id:
                continue
            jobs[index] = replace(
                item,
                last_run_at=last_run_at,
                next_run_at=next_run_at,
                last_result_json=_copy_json(last_result_json),
                failure_count=int(failure_count),
                status=status,
                updated_at=updated_at,
            )
            self.save(jobs)
            return jobs[index]
        return None

    def list_due_jobs(self, now: datetime) -> list[LearnerHeartbeatJob]:
        jobs = self.load()
        due = [
            job
            for job in jobs
            if job.status == "active" and job.next_run_at is not None and job.next_run_at <= now
        ]
        return sorted(due, key=lambda job: (job.next_run_at or now, job.created_at, job.job_id))

    def _mutate(
        self,
        job_id: str,
        updated_at: datetime,
        *,
        status: Literal["active", "paused", "stopped"],
    ) -> LearnerHeartbeatJob | None:
        jobs = self.load()
        for index, item in enumerate(jobs):
            if item.job_id != job_id:
                continue
            jobs[index] = replace(item, status=status, updated_at=updated_at)
            self.save(jobs)
            return jobs[index]
        return None


def new_job_id() -> str:
    return str(uuid.uuid4())
