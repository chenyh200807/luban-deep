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


def estimate_mastery(
    *,
    attempts: Iterable[Any] | None,
    legacy_score: Any = 0,
    required_question_count: int = 5,
) -> dict[str, Any]:
    valid_attempts = [_normalize_attempt(item) for item in list(attempts or [])]
    valid_attempts = [item for item in valid_attempts if item is not None]

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
    return {
        "score": score,
        "confidence": round(confidence, 2),
        "status": status,
        "sample_count": sample_count,
        "coverage_ratio": coverage_ratio,
        "last_practiced_at": last_practiced_at,
    }


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
