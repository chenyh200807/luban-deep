from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.training_intent import build_learning_training_intent


_TZ = timezone(timedelta(hours=8))
_PROJECTION_TTL = timedelta(hours=6)
_SEED_ROOT = Path(__file__).resolve().parents[3] / "data" / "seed"


def build_home_dashboard_learning_projection(
    *,
    projection: dict[str, Any] | None = None,
    weak_nodes: list[dict[str, Any]] | None = None,
    conversation_events: list[dict[str, Any]] | None = None,
    subject_id: str = "construction_exam_1",
    now: datetime | None = None,
) -> dict[str, Any]:
    del weak_nodes, conversation_events
    current_time = now or datetime.now(tz=_TZ)
    if _is_fresh_projection(projection, now=current_time):
        return _normalize_projection(projection)
    reason = "stale" if isinstance(projection, dict) else "missing"
    return _build_seed_fallback(subject_id=subject_id, fallback_reason=reason)


def _is_fresh_projection(projection: dict[str, Any] | None, *, now: datetime) -> bool:
    if not isinstance(projection, dict):
        return False
    if not _valid_focus(projection.get("today_focus")):
        return False
    if not _valid_prompts(projection.get("recommended_prompts")):
        return False
    generated_at = _parse_time(str(projection.get("generated_at") or ""))
    if generated_at is None:
        return False
    return now - generated_at <= _PROJECTION_TTL


def build_home_personalization_projection_from_learning_signal(
    payload: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any] | None:
    signal = dict(payload.get("next_training_signal") or {}) if isinstance(payload.get("next_training_signal"), dict) else {}
    concept = payload.get("concept") if isinstance(payload.get("concept"), dict) else {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    concept_label = _first_text(
        signal.get("focus"),
        signal.get("concept"),
        concept.get("label"),
    )
    error_label = _first_text(
        error.get("label"),
        _first_error_label(payload),
    )
    if not concept_label and not error_label:
        return None
    current_time = generated_at or datetime.now(tz=_TZ)
    prompt_concept = concept_label or "本次错因"
    prompt_error = error_label or "薄弱点"
    base_intent = {
        "concept_label": prompt_concept,
        "error_label": prompt_error,
        "subject_id": str(payload.get("subject_id") or "").strip(),
        "training_intent_id": payload.get("training_intent_id"),
        "evidence_refs": _evidence_refs(payload),
        "learning_state_ref": str(payload.get("learning_state_ref") or "").strip(),
        "suggested_mode": str(payload.get("suggested_mode") or payload.get("teaching_mode") or "").strip(),
    }
    prompts = [
        _projection_prompt(
            prompt_type="practice_prompt",
            text=f"用 3 道题训练{prompt_concept}",
            intent={**base_intent, "training_mode": "mixed_review", "reason": "home_projection_practice"},
        ),
        _projection_prompt(
            prompt_type="mistake_review",
            text=f"复盘{prompt_concept}里的{prompt_error}",
            intent={**base_intent, "training_mode": "mistake_repair", "reason": "home_projection_mistake"},
        ),
        _projection_prompt(
            prompt_type="concept_explain",
            text=f"讲清楚{prompt_concept}的关键判断",
            intent={**base_intent, "training_mode": "concept_explain", "reason": "home_projection_concept"},
        ),
    ]
    return {
        "generated_at": current_time.isoformat(),
        "source_status": {"fallback_used": False, "learning_report": "projection"},
        "today_focus": {
            "title": f"今日焦点：{prompt_concept}",
            "meta": "来自 learner_state.home_personalization",
            "prompt": prompts[0]["text"],
            "intent": prompts[0]["intent"],
        },
        "recommended_prompts": prompts,
    }


def write_home_personalization_projection(
    learner_state_service: Any,
    *,
    user_id: str,
    projection: dict[str, Any] | None,
) -> bool:
    if not isinstance(projection, dict):
        return False
    merger = getattr(learner_state_service, "merge_progress", None)
    if not callable(merger):
        return False
    merger(str(user_id or "").strip(), {"home_personalization": projection})
    return True


def _normalize_projection(projection: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(projection or {})
    source_status = dict(payload.get("source_status") or {})
    source_status.setdefault("fallback_used", False)
    source_status.setdefault("learning_report", "projection")
    payload["source_status"] = source_status
    return payload


def _valid_focus(value: Any) -> bool:
    return isinstance(value, dict) and bool(str(value.get("title") or "").strip())


def _valid_prompts(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(item, dict)
        and bool(str(item.get("text") or "").strip())
        and isinstance(item.get("intent"), dict)
        for item in value
    )


def _build_seed_fallback(*, subject_id: str, fallback_reason: str) -> dict[str, Any]:
    seed = _load_seed_prompts(subject_id)
    prompts = [
        _seed_prompt_to_dashboard_prompt(item)
        for item in list(seed.get("prompts") or [])[:3]
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if not prompts:
        intent = build_learning_training_intent(
            source="home_dashboard",
            reason="starter",
            training_mode="mixed_review",
            user_id="",
        )
        prompts = [{"prompt_type": "assessment", "text": "先做一次摸底测评", "intent": intent}]
    focus = dict(seed.get("today_focus") or {})
    if not focus:
        focus = {"title": "先做一题，给系统第一份学习证据", "meta": "starter"}
    focus["prompt"] = prompts[0]["text"]
    focus["intent"] = prompts[0]["intent"]
    return {
        "source_status": {
            "fallback_used": True,
            "fallback_reason": fallback_reason,
            "learning_report": "stale",
        },
        "today_focus": focus,
        "recommended_prompts": prompts,
    }


def _load_seed_prompts(subject_id: str) -> dict[str, Any]:
    path = _SEED_ROOT / str(subject_id or "") / "starter_prompts.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _seed_prompt_to_dashboard_prompt(item: dict[str, Any]) -> dict[str, Any]:
    prompt_type = str(item.get("prompt_type") or "starter").strip() or "starter"
    intent = build_learning_training_intent(
        source="home_dashboard",
        reason="starter",
        training_mode=str(item.get("training_mode") or "mixed_review"),
        user_id="",
    )
    seed_intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
    return {
        "prompt_type": prompt_type,
        "text": str(item.get("text") or "").strip(),
        "intent": {**intent, **seed_intent, "prompt_type": prompt_type},
    }


def _projection_prompt(*, prompt_type: str, text: str, intent: dict[str, Any]) -> dict[str, Any]:
    evidence_refs = _normalize_refs(intent.get("evidence_refs"))
    training_intent = build_learning_training_intent(
        source="home_dashboard",
        reason=str(intent.get("reason") or "home_projection"),
        training_mode=str(intent.get("training_mode") or "mixed_review"),
        concept_label=str(intent.get("concept_label") or "").strip(),
        error_label=str(intent.get("error_label") or "").strip(),
        evidence_refs=evidence_refs,
        user_id="",
    )
    learning_state_ref = str(intent.get("learning_state_ref") or "").strip()
    suggested_mode = str(intent.get("suggested_mode") or "").strip()
    return {
        "prompt_type": prompt_type,
        "text": text,
        "evidence_refs": evidence_refs,
        "learning_state_ref": learning_state_ref,
        "suggested_mode": suggested_mode,
        "intent": {
            **training_intent,
            "prompt_type": prompt_type,
            "subject_id": str(intent.get("subject_id") or "").strip(),
            "source_training_intent_id": intent.get("training_intent_id"),
            "learning_state_ref": learning_state_ref,
            "suggested_mode": suggested_mode,
        },
    }


def _evidence_refs(payload: dict[str, Any]) -> list[str]:
    refs = []
    for value in list(payload.get("evidence_refs") or []):
        text = str(value or "").strip()
        if text and text not in refs:
            refs.append(text)
    for key in ("event_id", "attempt_ref"):
        text = str(payload.get(key) or "").strip()
        if text and text not in refs:
            refs.append(text)
    return refs[:5]


def _normalize_refs(value: Any) -> list[str]:
    return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]


def _first_error_label(payload: dict[str, Any]) -> str:
    for error in list(payload.get("error_events") or payload.get("errors") or []):
        if not isinstance(error, dict):
            continue
        label = _first_text(error.get("error_label"), error.get("error_code"), error.get("diagnosis"))
        if label:
            return label
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_TZ)
    return parsed.astimezone(_TZ)


__all__ = [
    "build_home_dashboard_learning_projection",
    "build_home_personalization_projection_from_learning_signal",
    "write_home_personalization_projection",
]
