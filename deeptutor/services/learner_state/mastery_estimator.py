from __future__ import annotations

from datetime import datetime, timezone
from math import exp
from typing import Any, Iterable

_DIFFICULTY_WEIGHTS = {
    "easy": 0.85,
    "medium": 1.0,
    "normal": 1.0,
    "hard": 1.15,
    "difficult": 1.15,
    "high": 1.15,
}


# Phase -1 Decision 4 / Batch B Task 5: tiered forgetting-decay profiles.
# Half-life days per ability_dimension; revalidation_schedule informs the
# ARRS-style scheduler downstream. This map is the SINGLE place to tune
# decay; consumers must not hard-code a 14-day default elsewhere.
DECAY_PROFILES: dict[str, dict[str, Any]] = {
    "code_application": {"decay_half_life_days": 10, "revalidation_schedule": (3, 7, 14, 30)},
    "calculation":      {"decay_half_life_days": 14, "revalidation_schedule": (3, 7, 14, 30)},
    "question_reading": {"decay_half_life_days": 21, "revalidation_schedule": (7, 14, 30)},
    "expression":       {"decay_half_life_days": 21, "revalidation_schedule": (7, 14, 30)},
    "transfer":         {"decay_half_life_days": 28, "revalidation_schedule": (14, 30, 60)},
    "review_execution": {"decay_half_life_days": 14, "revalidation_schedule": (7, 14, 30)},
}
_DEFAULT_DECAY_PROFILE: dict[str, Any] = {
    "decay_half_life_days": 14,
    "revalidation_schedule": (7, 14, 30),
}


def estimate_mastery(
    *,
    attempts: Iterable[Any] | None,
    legacy_score: Any = 0,
    required_question_count: int = 5,
    ability_dimension: str = "",
    now_iso: str = "",
) -> dict[str, Any]:
    valid_attempts = [_normalize_attempt(item) for item in list(attempts or [])]
    valid_attempts = [item for item in valid_attempts if item is not None]

    decay_profile = _resolve_decay_profile(ability_dimension)
    now = _parse_iso(now_iso) or datetime.now(timezone.utc)

    sample_count = len(valid_attempts)
    last_practiced_at = max((str(item.get("created_at") or "") for item in valid_attempts), default="")
    unique_questions = {
        str(item.get("question_id") or item.get("attempt_id") or index)
        for index, item in enumerate(valid_attempts)
    }
    required_count = max(1, int(required_question_count or 5))
    coverage_ratio = round(min(len(unique_questions) / required_count, 1), 2)

    if sample_count <= 0:
        confidence = 0.2
        score = min(_safe_int(legacy_score), 60)
        return {
            "score": score,
            "confidence": confidence,
            "status": "insufficient_evidence",
            "sample_count": 0,
            "coverage_ratio": 0,
            "last_practiced_at": "",
            "level": "insufficient_evidence",
            "forgetting_risk": 0,
            "needs_revalidation": False,
            "decay_profile_days": int(decay_profile["decay_half_life_days"]),
        }

    correct_count = sum(1 for item in valid_attempts if bool(item.get("correct")))
    accuracy = correct_count / max(sample_count, 1)
    difficulty_diversity = min(
        len({str(item.get("difficulty") or "medium") for item in valid_attempts}) / 3,
        1,
    )
    sample_depth = min(sample_count / 3, 1)
    sample_diversity = difficulty_diversity * sample_depth
    confidence = min(0.95, 0.2 + 0.5 * coverage_ratio + 0.3 * sample_diversity)
    if _has_conflicting_evidence(accuracy=accuracy, sample_count=sample_count):
        confidence = min(confidence, 0.69)

    bayesian_accuracy = (correct_count + 1) / (sample_count + 2)
    difficulty_weight = sum(float(item.get("difficulty_weight") or 1.0) for item in valid_attempts) / sample_count
    recency_weight = _recency_weight(last_practiced_at)
    evidence_score = round(bayesian_accuracy * difficulty_weight * recency_weight * 100)
    legacy = _safe_int(legacy_score)
    blended_score = round(evidence_score * 0.75 + legacy * 0.25) if legacy else evidence_score
    score = max(0, min(blended_score, _confidence_cap(confidence)))

    status = _status(confidence=confidence, accuracy=accuracy, sample_count=sample_count)

    # Phase -1 Decision 4 / Task 5: recency-aware confidence & forgetting risk.
    sorted_attempts = sorted(
        valid_attempts,
        key=lambda item: str(item.get("created_at") or ""),
    )
    most_recent = sorted_attempts[-1]
    most_recent_correct = bool(most_recent.get("correct"))
    most_recent_age = _age_days(str(most_recent.get("created_at") or ""), now)
    forgetting_risk = _forgetting_risk_from_recent(
        most_recent_correct=most_recent_correct,
        most_recent_age_days=most_recent_age,
        decay_profile=decay_profile,
    )
    level = _classify_level(
        sample_count=sample_count,
        correct_count=correct_count,
        most_recent_correct=most_recent_correct,
        forgetting_risk=forgetting_risk,
    )
    needs_revalidation = (
        forgetting_risk > 0.5
        or level in {"needs_revalidation", "weak", "unstable"}
    )

    return {
        "score": score,
        "confidence": round(confidence, 2),
        "status": status,
        "sample_count": sample_count,
        "coverage_ratio": coverage_ratio,
        "last_practiced_at": last_practiced_at,
        "level": level,
        "forgetting_risk": round(forgetting_risk, 3),
        "needs_revalidation": needs_revalidation,
        "decay_profile_days": int(decay_profile["decay_half_life_days"]),
    }


def _resolve_decay_profile(ability_dimension: str) -> dict[str, Any]:
    return DECAY_PROFILES.get(str(ability_dimension or "").strip(), _DEFAULT_DECAY_PROFILE)


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(created_at: str, now: datetime) -> float:
    parsed = _parse_iso(created_at)
    if parsed is None:
        return 0.0
    delta = (now - parsed).total_seconds() / 86400
    return max(delta, 0.0)


def _forgetting_risk_from_recent(
    *,
    most_recent_correct: bool,
    most_recent_age_days: float,
    decay_profile: dict[str, Any],
) -> float:
    """Risk = 1 - exp(-age / half_life). When the most recent attempt is
    a miss, mastery is already in question — the floor reflects that.
    When it is a correct revalidation, age drives the exponential decay."""
    half_life = float(decay_profile.get("decay_half_life_days") or 14)
    if half_life <= 0:
        half_life = 14
    decay = 1.0 - exp(-most_recent_age_days / half_life)
    decay = max(0.0, min(1.0, decay))
    if not most_recent_correct:
        return max(decay, 0.6)
    return decay


def _classify_level(
    *,
    sample_count: int,
    correct_count: int,
    most_recent_correct: bool,
    forgetting_risk: float,
) -> str:
    if sample_count <= 0:
        return "insufficient_evidence"
    if sample_count == 1:
        if not most_recent_correct:
            return "observed"
        if forgetting_risk > 0.5:
            return "needs_revalidation"
        return "observed"
    wrong_count = sample_count - correct_count
    if correct_count == 0:
        return "weak"
    if wrong_count == 0:
        if forgetting_risk > 0.5:
            return "needs_revalidation"
        if forgetting_risk >= 0.4:
            return "unstable"
        return "stable"
    # mixed
    if most_recent_correct:
        return "improving"
    return "unstable"


def _normalize_attempt(item: Any) -> dict[str, Any] | None:
    payload = _payload(item)
    if _is_conversation_only(payload, item):
        return None
    if _safe_dict(payload.get("quality")).get("progress_countable") is False:
        return None

    correct = _is_correct(payload)
    difficulty = _difficulty(payload)
    return {
        "attempt_id": str(payload.get("attempt_id") or payload.get("event_id") or ""),
        "question_id": str(payload.get("question_id") or payload.get("source_id") or ""),
        "created_at": str(payload.get("created_at") or getattr(item, "created_at", "") or ""),
        "correct": correct,
        "difficulty": difficulty,
        "difficulty_weight": _DIFFICULTY_WEIGHTS.get(difficulty, 1.0),
    }


def _payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        payload = dict(_safe_dict(item.get("payload_json")) or item)
    else:
        payload = dict(_safe_dict(getattr(item, "payload_json", {})))
    if "created_at" not in payload and str(getattr(item, "created_at", "") or ""):
        payload["created_at"] = str(getattr(item, "created_at", "") or "")
    if "source_feature" not in payload and str(getattr(item, "source_feature", "") or ""):
        payload["source_feature"] = str(getattr(item, "source_feature", "") or "")
    if "source_id" not in payload and str(getattr(item, "source_id", "") or ""):
        payload["source_id"] = str(getattr(item, "source_id", "") or "")
    if "event_id" not in payload and str(getattr(item, "event_id", "") or ""):
        payload["event_id"] = str(getattr(item, "event_id", "") or "")
    return payload


def _is_conversation_only(payload: dict[str, Any], item: Any) -> bool:
    source = str(payload.get("evidence_source") or payload.get("source_feature") or "").strip()
    if not source and not isinstance(item, dict):
        source = str(getattr(item, "source_feature", "") or "").strip()
    return source == "conversation_synthesis"


def _is_correct(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("correct"), bool):
        return bool(payload.get("correct"))
    if isinstance(payload.get("is_correct"), bool):
        return bool(payload.get("is_correct"))
    # Phase -1 Decision 4 / Task 5: callers (synthesis / read model) may
    # pass a normalized ``score_ratio`` float instead of the raw awarded
    # / max_score pair. Treat ratio >= 1.0 as correct.
    if "score_ratio" in payload:
        try:
            return float(payload.get("score_ratio") or 0) >= 1.0
        except (TypeError, ValueError):
            return False
    try:
        awarded = float(payload.get("score_awarded") or 0)
        max_score = float(payload.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return max_score > 0 and awarded >= max_score


def _difficulty(payload: dict[str, Any]) -> str:
    raw = str(
        payload.get("difficulty")
        or payload.get("question_difficulty")
        or payload.get("difficulty_level")
        or "medium"
    ).strip().lower()
    return raw if raw in _DIFFICULTY_WEIGHTS else "medium"


def _recency_weight(value: str) -> float:
    if not value:
        return 0.9
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.9
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = max((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 86400, 0)
    return 0.85 + 0.15 * exp(-age_days / 14)


def _has_conflicting_evidence(*, accuracy: float, sample_count: int) -> bool:
    return sample_count >= 3 and 0.35 <= accuracy <= 0.65


def _confidence_cap(confidence: float) -> int:
    if confidence < 0.4:
        return 60
    if confidence < 0.7:
        return 78
    return 100


def _status(*, confidence: float, accuracy: float, sample_count: int) -> str:
    if confidence < 0.4:
        return "insufficient_evidence"
    if _has_conflicting_evidence(accuracy=accuracy, sample_count=sample_count):
        return "needs_confirmation"
    if accuracy < 0.7:
        return "developing"
    if confidence < 0.7:
        return "developing"
    return "stable"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return max(0, min(int(round(float(value or 0))), 100))
    except (TypeError, ValueError):
        return 0
