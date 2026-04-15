from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .service import LearnerHeartbeatService
from .store import LearnerHeartbeatJob, _coerce_datetime


class LearnerHeartbeatScheduler:
    """Run one learner-heartbeat scan cycle against due jobs."""

    def __init__(
        self,
        service: LearnerHeartbeatService | None = None,
        executor: Callable[[LearnerHeartbeatJob], Awaitable[Any] | Any] | None = None,
    ) -> None:
        self._service = service or LearnerHeartbeatService()
        self._executor = executor or self._default_executor

    @staticmethod
    async def _default_executor(job: LearnerHeartbeatJob) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "user_id": job.user_id,
            "bot_id": job.bot_id,
            "channel": job.channel,
        }

    @staticmethod
    def _normalize_result(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            return {"message": value}
        return {"value": value}

    async def _invoke_executor(self, job: LearnerHeartbeatJob) -> dict[str, Any]:
        outcome = self._executor(job)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return self._normalize_result(outcome)

    async def run_once(
        self,
        *,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        current = _coerce_datetime(now) if now is not None else datetime.now(timezone.utc).astimezone()
        if current is None:
            current = datetime.now(timezone.utc).astimezone()

        due_jobs = self._service.list_due_jobs(now=current)
        if limit is not None:
            due_jobs = due_jobs[: max(0, int(limit))]

        results: list[dict[str, Any]] = []
        for job in due_jobs:
            try:
                payload = await self._invoke_executor(job)
                updated = self._service.record_run_result(
                    user_id=job.user_id,
                    job_id=job.job_id,
                    success=True,
                    result_json=payload,
                    finished_at=current,
                )
                results.append(
                    {
                        "job_id": job.job_id,
                        "status": "ok",
                        "result": payload,
                        "job": updated.to_dict(),
                    }
                )
            except Exception as exc:
                updated = self._service.record_run_result(
                    user_id=job.user_id,
                    job_id=job.job_id,
                    success=False,
                    result_json={
                        "error": str(exc),
                        "exception_type": exc.__class__.__name__,
                    },
                    finished_at=current,
                )
                results.append(
                    {
                        "job_id": job.job_id,
                        "status": "error",
                        "error": str(exc),
                        "job": updated.to_dict(),
                    }
                )

        return results


__all__ = ["LearnerHeartbeatScheduler"]
