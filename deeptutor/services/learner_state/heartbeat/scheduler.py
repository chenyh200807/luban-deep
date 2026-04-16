from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from .arbitration import LearnerHeartbeatArbitrationHints, LearnerHeartbeatArbitrationResult, LearnerHeartbeatArbitrator
from .service import LearnerHeartbeatService
from .store import LearnerHeartbeatJob, _coerce_datetime


class LearnerHeartbeatScheduler:
    """Run one learner-heartbeat scan cycle against due jobs."""

    def __init__(
        self,
        service: LearnerHeartbeatService | None = None,
        executor: Callable[[LearnerHeartbeatJob], Awaitable[Any] | Any] | None = None,
        arbitrator: LearnerHeartbeatArbitrator | None = None,
        hint_resolver: Callable[
            [str, list[LearnerHeartbeatJob]],
            LearnerHeartbeatArbitrationHints | dict[str, Any] | None | Awaitable[LearnerHeartbeatArbitrationHints | dict[str, Any] | None],
        ]
        | None = None,
        suppression_cooldown_minutes: int = 15,
    ) -> None:
        self._service = service or LearnerHeartbeatService()
        self._executor = executor or self._default_executor
        self._arbitrator = arbitrator or LearnerHeartbeatArbitrator()
        self._hint_resolver = hint_resolver
        self._suppression_cooldown_minutes = max(1, int(suppression_cooldown_minutes or 15))

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

    @staticmethod
    def _normalize_hints(
        value: LearnerHeartbeatArbitrationHints | dict[str, Any] | None,
    ) -> LearnerHeartbeatArbitrationHints:
        if value is None:
            return LearnerHeartbeatArbitrationHints()
        if isinstance(value, LearnerHeartbeatArbitrationHints):
            return value
        if isinstance(value, dict):
            return LearnerHeartbeatArbitrationHints(
                active_plan_bot_id=value.get("active_plan_bot_id"),
                learner_goal_urgency_by_bot_id=dict(value.get("learner_goal_urgency_by_bot_id") or {}),
                recent_interaction_source_by_bot_id=dict(value.get("recent_interaction_source_by_bot_id") or {}),
                overlay_heartbeat_override_by_bot_id=dict(value.get("overlay_heartbeat_override_by_bot_id") or {}),
                recently_contacted_until_by_bot_id=dict(value.get("recently_contacted_until_by_bot_id") or {}),
            )
        raise TypeError(f"unsupported arbitration hints: {type(value)!r}")

    async def _resolve_hints(
        self,
        *,
        user_id: str,
        jobs: list[LearnerHeartbeatJob],
    ) -> LearnerHeartbeatArbitrationHints:
        if self._hint_resolver is None:
            return LearnerHeartbeatArbitrationHints()
        outcome = self._hint_resolver(user_id, jobs)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return self._normalize_hints(outcome)

    @staticmethod
    def _serialize_arbitration_result(
        result: LearnerHeartbeatArbitrationResult,
    ) -> dict[str, Any]:
        return {
            "user_id": result.user_id,
            "winner_job_id": result.winner_job_id,
            "winner_bot_id": result.winner_bot_id,
            "winner_score": result.winner_score,
            "suppressed_bot_ids": list(result.suppressed_bot_ids),
            "suppressed_reasons": {
                key: list(value)
                for key, value in dict(result.suppressed_reasons).items()
            },
            "reasons": list(result.reasons),
            "decisions": [
                {
                    "job_id": decision.job_id,
                    "bot_id": decision.bot_id,
                    "score": decision.score,
                    "reasons": list(decision.reasons),
                    "score_breakdown": dict(decision.score_breakdown),
                    "suppressed": bool(decision.suppressed),
                    "suppression_reason": decision.suppression_reason,
                }
                for decision in result.decisions
            ],
        }

    def _suppression_payload(
        self,
        *,
        job: LearnerHeartbeatJob,
        arbitration_result: LearnerHeartbeatArbitrationResult,
        recorded_at: datetime,
    ) -> dict[str, Any]:
        recorded_at_iso = recorded_at.isoformat()
        conversation_id = f"learner-heartbeat:{job.user_id}:{job.channel}"
        return {
            "success": True,
            "recorded_at": recorded_at_iso,
            "job_id": job.job_id,
            "user_id": job.user_id,
            "bot_id": job.bot_id,
            "channel": job.channel,
            "delivery_state": "suppressed",
            "delivery": {
                "state": "suppressed",
                "channel": job.channel,
                "bot_id": job.bot_id,
                "user_id": job.user_id,
                "conversation_id": conversation_id,
            },
            "audit": {
                "job_id": job.job_id,
                "user_id": job.user_id,
                "bot_id": job.bot_id,
                "channel": job.channel,
                "source": "learner_heartbeat",
                "conversation_id": conversation_id,
                "status": "suppressed",
                "success": True,
                "recorded_at": recorded_at_iso,
            },
            "suppression_reason": list(arbitration_result.suppressed_reasons.get(job.bot_id, ())),
            "arbitration": self._serialize_arbitration_result(arbitration_result),
        }

    async def run_once(
        self,
        *,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        current = _coerce_datetime(now) if now is not None else datetime.now(timezone.utc).astimezone()
        if current is None:
            current = datetime.now(timezone.utc).astimezone()

        due_jobs = self._service.get_due_jobs(now=current)
        results: list[dict[str, Any]] = []
        grouped_jobs: dict[str, list[LearnerHeartbeatJob]] = {}
        user_order: list[str] = []
        for job in due_jobs:
            if job.user_id not in grouped_jobs:
                grouped_jobs[job.user_id] = []
                user_order.append(job.user_id)
            grouped_jobs[job.user_id].append(job)

        arbitration_plans: list[dict[str, Any]] = []
        for user_id in user_order:
            jobs = list(grouped_jobs.get(user_id, []))
            if not jobs:
                continue
            winner = jobs[0]
            suppressed: list[LearnerHeartbeatJob] = []
            arbitration_result: LearnerHeartbeatArbitrationResult | None = None
            if len(jobs) > 1:
                hints = await self._resolve_hints(user_id=user_id, jobs=jobs)
                arbitration_result = self._arbitrator.arbitrate(
                    user_id,
                    jobs,
                    hints=hints,
                    now=current,
                )
                if arbitration_result.winner_job_id:
                    winner = next(
                        (item for item in jobs if item.job_id == arbitration_result.winner_job_id),
                        winner,
                    )
                suppressed = [item for item in jobs if item.job_id != winner.job_id]
            arbitration_plans.append(
                {
                    "winner": winner,
                    "suppressed": suppressed,
                    "arbitration_result": arbitration_result,
                }
            )

        if limit is not None:
            arbitration_plans = arbitration_plans[: max(0, int(limit))]

        for plan in arbitration_plans:
            job = plan["winner"]
            suppressed_jobs = list(plan.get("suppressed") or [])
            arbitration_result = plan.get("arbitration_result")
            arbitration_payload = (
                self._serialize_arbitration_result(arbitration_result)
                if isinstance(arbitration_result, LearnerHeartbeatArbitrationResult)
                else None
            )

            for suppressed_job in suppressed_jobs:
                deferred = self._service.mark_run(
                    job_id=suppressed_job.job_id,
                    next_run_at=current + timedelta(minutes=self._suppression_cooldown_minutes),
                    last_result_json=(
                        self._suppression_payload(
                            job=suppressed_job,
                            arbitration_result=arbitration_result,
                            recorded_at=current,
                        )
                        if isinstance(arbitration_result, LearnerHeartbeatArbitrationResult)
                        else {}
                    ),
                    failure_count=int(suppressed_job.failure_count),
                    status=suppressed_job.status,
                    last_run_at=current,
                )
                results.append(
                    {
                        "job_id": suppressed_job.job_id,
                        "status": "suppressed",
                        "job": (deferred.to_dict() if deferred is not None else suppressed_job.to_dict()),
                        **({"arbitration": arbitration_payload} if arbitration_payload is not None else {}),
                    }
                )

            try:
                payload = await self._invoke_executor(job)
                if arbitration_payload is not None:
                    payload = {
                        **payload,
                        "arbitration": arbitration_payload,
                    }
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
                        **({"arbitration": arbitration_payload} if arbitration_payload is not None else {}),
                    }
                )
            except Exception as exc:
                error_payload = {
                    "error": str(exc),
                    "exception_type": exc.__class__.__name__,
                }
                if arbitration_payload is not None:
                    error_payload["arbitration"] = arbitration_payload
                updated = self._service.record_run_result(
                    user_id=job.user_id,
                    job_id=job.job_id,
                    success=False,
                    result_json=error_payload,
                    finished_at=current,
                )
                results.append(
                    {
                        "job_id": job.job_id,
                        "status": "error",
                        "error": str(exc),
                        "job": updated.to_dict(),
                        **({"arbitration": arbitration_payload} if arbitration_payload is not None else {}),
                    }
                )

        return results


__all__ = ["LearnerHeartbeatScheduler"]
