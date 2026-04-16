from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Any, Sequence

try:
    from .store import LearnerHeartbeatJob, _coerce_datetime
except Exception:  # pragma: no cover - allows direct module loading in tests
    _STORE_PATH = Path(__file__).with_name("store.py")
    _STORE_SPEC = importlib.util.spec_from_file_location(
        "deeptutor_services_learner_state_heartbeat_store",
        _STORE_PATH,
    )
    if _STORE_SPEC is None or _STORE_SPEC.loader is None:
        raise
    _STORE_MODULE = importlib.util.module_from_spec(_STORE_SPEC)
    _STORE_SPEC.loader.exec_module(_STORE_MODULE)
    LearnerHeartbeatJob = _STORE_MODULE.LearnerHeartbeatJob
    _coerce_datetime = _STORE_MODULE._coerce_datetime

_RECENT_INTERACTION_WEIGHTS = {
    "manual": 15,
    "user_reply": 12,
    "learner_reply": 12,
    "turn": 10,
    "guide": 8,
    "notebook": 6,
    "heartbeat": 4,
}


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _normalize_score(value: Any, *, minimum: int = 0, maximum: int = 100) -> int:
    try:
        score = int(value)
    except Exception:
        return minimum
    return max(minimum, min(maximum, score))


def _overlay_priority_bonus(override: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if bool(override.get("suppress")):
        reasons.append("overlay_override_suppress")
        return -10_000, reasons
    bonus = 0
    if bool(override.get("force_winner")):
        bonus += 100
        reasons.append("overlay_force_winner:+100")
    raw_priority = override.get("priority_bonus", override.get("priority"))
    if raw_priority is not None:
        priority_bonus = _normalize_score(raw_priority, minimum=-20, maximum=40)
        bonus += priority_bonus
        reasons.append(f"overlay_priority={raw_priority}=>{priority_bonus:+d}")
    if bonus:
        reasons.append(f"overlay_bonus_total={bonus:+d}")
    return bonus, reasons


@dataclass(frozen=True)
class LearnerHeartbeatArbitrationHints:
    active_plan_bot_id: str | None = None
    learner_goal_urgency_by_bot_id: dict[str, int] = field(default_factory=dict)
    recent_interaction_source_by_bot_id: dict[str, str] = field(default_factory=dict)
    overlay_heartbeat_override_by_bot_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    recently_contacted_until_by_bot_id: dict[str, datetime | str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class LearnerHeartbeatArbitrationDecision:
    job_id: str
    bot_id: str
    score: int
    reasons: tuple[str, ...]
    score_breakdown: dict[str, int] = field(default_factory=dict)
    suppressed: bool = False
    suppression_reason: str | None = None


@dataclass(frozen=True)
class LearnerHeartbeatArbitrationResult:
    user_id: str
    winner_job_id: str | None
    winner_bot_id: str | None
    winner_score: int | None
    suppressed_bot_ids: tuple[str, ...]
    suppressed_reasons: dict[str, tuple[str, ...]]
    decisions: tuple[LearnerHeartbeatArbitrationDecision, ...]
    reasons: tuple[str, ...] = ()


class LearnerHeartbeatArbitrator:
    """Pick one learner-heartbeat winner per user from due jobs."""

    def arbitrate(
        self,
        user_id: str,
        jobs: Sequence[LearnerHeartbeatJob],
        *,
        hints: LearnerHeartbeatArbitrationHints | None = None,
        now: datetime | str | None = None,
    ) -> LearnerHeartbeatArbitrationResult:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("user_id is required")

        normalized_jobs = list(jobs)
        if not normalized_jobs:
            return LearnerHeartbeatArbitrationResult(
                user_id=normalized_user_id,
                winner_job_id=None,
                winner_bot_id=None,
                winner_score=None,
                suppressed_bot_ids=(),
                suppressed_reasons={},
                decisions=(),
                reasons=("no_due_jobs",),
            )

        for job in normalized_jobs:
            if _normalize_text(job.user_id) != normalized_user_id:
                raise ValueError("all jobs must belong to the same user_id")

        current = _coerce_datetime(now) if now is not None else _now()
        if current is None:
            current = _now()

        hints = hints or LearnerHeartbeatArbitrationHints()
        decisions = [
            self._score_job(job, hints=hints, now=current)
            for job in normalized_jobs
        ]

        eligible = [decision for decision in decisions if not decision.suppressed]
        suppressed_bot_ids: list[str] = [
            decision.bot_id for decision in decisions if decision.suppressed
        ]
        suppressed_reasons: dict[str, tuple[str, ...]] = {
            decision.bot_id: decision.reasons
            for decision in decisions
            if decision.suppressed
        }

        if not eligible:
            return LearnerHeartbeatArbitrationResult(
                user_id=normalized_user_id,
                winner_job_id=None,
                winner_bot_id=None,
                winner_score=None,
                suppressed_bot_ids=tuple(dict.fromkeys(suppressed_bot_ids)),
                suppressed_reasons=suppressed_reasons,
                decisions=tuple(decisions),
                reasons=("all_jobs_suppressed",),
            )

        winner = max(eligible, key=self._decision_rank_key)
        winner_reason = tuple(winner.reasons)
        loser_reasons: dict[str, tuple[str, ...]] = dict(suppressed_reasons)

        for decision in decisions:
            if decision.job_id == winner.job_id:
                continue
            if not decision.suppressed:
                loser_reasons[decision.bot_id] = decision.reasons + (
                    f"suppressed_by_winner={winner.bot_id}",
                    f"winner_score={winner.score}",
                    f"loser_score={decision.score}",
                )
                suppressed_bot_ids.append(decision.bot_id)

        return LearnerHeartbeatArbitrationResult(
            user_id=normalized_user_id,
            winner_job_id=winner.job_id,
            winner_bot_id=winner.bot_id,
            winner_score=winner.score,
            suppressed_bot_ids=tuple(dict.fromkeys(suppressed_bot_ids)),
            suppressed_reasons=loser_reasons,
            decisions=tuple(sorted(decisions, key=self._decision_rank_key, reverse=True)),
            reasons=winner_reason or ("winner_selected",),
        )

    def _score_job(
        self,
        job: LearnerHeartbeatJob,
        *,
        hints: LearnerHeartbeatArbitrationHints,
        now: datetime,
    ) -> LearnerHeartbeatArbitrationDecision:
        bot_id = _normalize_text(job.bot_id)
        score = 0
        reasons: list[str] = []
        score_breakdown: dict[str, int] = {}

        if bot_id and bot_id == _normalize_text(hints.active_plan_bot_id):
            score += 50
            score_breakdown["active_plan"] = 50
            reasons.append("active_plan_match:+50")

        goal_urgency = _normalize_score(hints.learner_goal_urgency_by_bot_id.get(bot_id, 0), maximum=10)
        if goal_urgency > 0:
            bonus = min(30, goal_urgency * 5)
            score += bonus
            score_breakdown["goal_urgency"] = bonus
            reasons.append(f"learner_goal_urgency={goal_urgency}=>+{bonus}")

        recent_source = _normalize_text(hints.recent_interaction_source_by_bot_id.get(bot_id))
        if recent_source:
            bonus = _RECENT_INTERACTION_WEIGHTS.get(recent_source, 3)
            score += bonus
            score_breakdown["recent_interaction"] = bonus
            reasons.append(f"recent_interaction_source={recent_source}=>+{bonus}")

        overlay_override = dict(hints.overlay_heartbeat_override_by_bot_id.get(bot_id) or {})
        if overlay_override:
            bonus, overlay_reasons = _overlay_priority_bonus(overlay_override)
            if bonus <= -10_000:
                return LearnerHeartbeatArbitrationDecision(
                    job_id=job.job_id,
                    bot_id=bot_id,
                    score=-10_000,
                    reasons=tuple(overlay_reasons or ("overlay_override_suppressed",)),
                    score_breakdown={**score_breakdown, "overlay_override": -10_000},
                    suppressed=True,
                    suppression_reason="overlay_override_suppress",
                )
            if bonus:
                score += bonus
                score_breakdown["overlay_override"] = bonus
                reasons.extend(overlay_reasons)

        cooldown_until = hints.recently_contacted_until_by_bot_id.get(bot_id)
        parsed_cooldown_until = _coerce_datetime(cooldown_until) if cooldown_until is not None else None
        if parsed_cooldown_until is not None and now < parsed_cooldown_until:
            reason = f"recently_contacted_cooldown_until={parsed_cooldown_until.isoformat()}"
            return LearnerHeartbeatArbitrationDecision(
                job_id=job.job_id,
                bot_id=bot_id,
                score=-5_000,
                reasons=tuple(reasons + [reason]),
                score_breakdown={**score_breakdown, "cooldown": -5_000},
                suppressed=True,
                suppression_reason=reason,
            )

        if not reasons:
            reasons.append("no_hint_bonus")

        return LearnerHeartbeatArbitrationDecision(
            job_id=job.job_id,
            bot_id=bot_id,
            score=score,
            reasons=tuple(reasons),
            score_breakdown=score_breakdown,
        )

    @staticmethod
    def _decision_rank_key(decision: LearnerHeartbeatArbitrationDecision) -> tuple[int, int, int, str, str]:
        active_plan_score = decision.score_breakdown.get("active_plan", 0)
        urgency_score = decision.score_breakdown.get("goal_urgency", 0)
        interaction_score = decision.score_breakdown.get("recent_interaction", 0)
        return (
            decision.score,
            active_plan_score,
            urgency_score + interaction_score,
            decision.bot_id,
            decision.job_id,
        )


__all__ = [
    "LearnerHeartbeatArbitrationDecision",
    "LearnerHeartbeatArbitrationHints",
    "LearnerHeartbeatArbitrationResult",
    "LearnerHeartbeatArbitrator",
]
