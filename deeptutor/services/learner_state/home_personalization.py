from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.training_intent import build_learning_training_intent
from deeptutor.services.taxonomy.learning_topic_resolver import (
    TopicInferer,
    canonical_learning_topic_label,
    infer_learning_topic_with_llm,
    normalize_learning_topic_text,
    resolve_learning_topic_from_payload,
)


_TZ = timezone(timedelta(hours=8))
_PROJECTION_TTL = timedelta(hours=6)
_SEED_ROOT = Path(__file__).resolve().parents[3] / "data" / "seed"
_SIX_ACTION_PROMPT_TYPES = {
    "practice_prompt",
    "mistake_review",
    "concept_explain",
    "exam_transfer",
    "knowledge_map",
    "quick_check",
}


def build_home_dashboard_learning_projection(
    *,
    projection: dict[str, Any] | None = None,
    weak_nodes: list[dict[str, Any]] | None = None,
    conversation_events: list[dict[str, Any]] | None = None,
    subject_id: str = "construction_exam_1",
    now: datetime | None = None,
) -> dict[str, Any]:
    del weak_nodes
    current_time = now or datetime.now(tz=_TZ)
    if _is_fresh_projection(projection, now=current_time):
        return _normalize_projection(projection)
    reason = "stale" if isinstance(projection, dict) else "missing"
    recovered_projection = _projection_from_recent_learning_events(
        conversation_events,
        generated_at=current_time,
    )
    if recovered_projection:
        source_status = dict(recovered_projection.get("source_status") or {})
        source_status["recovered_from"] = "learner_memory_events.learning_evidence"
        source_status["projection_state"] = reason
        recovered_projection["source_status"] = source_status
        return recovered_projection
    return _build_seed_fallback(subject_id=subject_id, fallback_reason=reason)


def _is_fresh_projection(projection: dict[str, Any] | None, *, now: datetime) -> bool:
    if not isinstance(projection, dict):
        return False
    if not _valid_focus(projection.get("today_focus")):
        return False
    if not _valid_prompts(projection.get("recommended_prompts")):
        return False
    if not _valid_focus_prompt_link(
        projection.get("today_focus"),
        projection.get("recommended_prompts"),
    ):
        return False
    generated_at = _parse_time(str(projection.get("generated_at") or ""))
    if generated_at is None:
        return False
    return now - generated_at <= _PROJECTION_TTL


def build_home_personalization_projection_from_learning_signal(
    payload: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    llm_topic_inferer: TopicInferer | None = None,
) -> dict[str, Any] | None:
    signal = dict(payload.get("next_training_signal") or {}) if isinstance(payload.get("next_training_signal"), dict) else {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    topic = resolve_learning_topic_from_payload(
        payload,
        llm_topic_inferer=llm_topic_inferer or infer_learning_topic_with_llm,
    )
    if topic is None:
        return None
    explicit_label = _explicit_concept_label(payload)
    concept_label = explicit_label if explicit_label and topic.confidence == "low" else topic.label
    error_label = _first_focus_topic_label(
        error.get("label"),
        _first_error_label(payload),
    )
    if not concept_label:
        return None
    current_time = generated_at or datetime.now(tz=_TZ)
    prompt_concept = concept_label
    prompt_error = error_label or "薄弱点"
    base_intent = {
        "concept_label": prompt_concept,
        "error_label": prompt_error,
        "subject_id": str(payload.get("subject_id") or "").strip(),
        "training_intent_id": payload.get("training_intent_id"),
        "evidence_refs": _evidence_refs(payload),
        "learning_state_ref": str(payload.get("learning_state_ref") or "").strip(),
        "suggested_mode": str(payload.get("suggested_mode") or payload.get("teaching_mode") or "").strip(),
        **topic.intent_fields(),
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
        _projection_prompt(
            prompt_type="exam_transfer",
            text=f"用一道真题场景理解{prompt_concept}",
            intent={**base_intent, "training_mode": "case_repair", "reason": "home_projection_exam_transfer"},
        ),
        _projection_prompt(
            prompt_type="knowledge_map",
            text=f"梳理{prompt_concept}的高频考点",
            intent={**base_intent, "training_mode": "rubric_recall", "reason": "home_projection_knowledge_map"},
        ),
        _projection_prompt(
            prompt_type="quick_check",
            text=f"用 1 个小问题验证{prompt_concept}是否真会了",
            intent={**base_intent, "training_mode": "mcq_discrimination", "reason": "home_projection_quick_check"},
        ),
    ]
    if str(payload.get("learning_signal_type") or "").strip() == "training_completed":
        prompts = [
            _assessment_retest_prompt(
                text=f"再测一次{prompt_concept}",
                intent={**base_intent, "reason": "training_completion_retest"},
            ),
            *prompts[:2],
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
    if not _valid_focus(projection.get("today_focus")) or not _valid_prompts(
        projection.get("recommended_prompts")
    ):
        return False
    if not _valid_focus_prompt_link(projection.get("today_focus"), projection.get("recommended_prompts")):
        return False
    merger = getattr(learner_state_service, "merge_progress", None)
    if not callable(merger):
        return False
    merger(str(user_id or "").strip(), {"home_personalization": projection})
    return True


def _normalize_projection(projection: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(projection or {})
    upgraded = _upgrade_legacy_home_projection(payload)
    if upgraded is not None:
        payload = upgraded
    source_status = dict(payload.get("source_status") or {})
    source_status.setdefault("fallback_used", False)
    source_status.setdefault("learning_report", "projection")
    payload["source_status"] = source_status
    return payload


def _upgrade_legacy_home_projection(projection: dict[str, Any]) -> dict[str, Any] | None:
    prompts = [item for item in list(projection.get("recommended_prompts") or []) if isinstance(item, dict)]
    prompt_types = {str(item.get("prompt_type") or "").strip() for item in prompts}
    if _SIX_ACTION_PROMPT_TYPES.issubset(prompt_types):
        return None
    if not {"practice_prompt", "mistake_review", "concept_explain"}.issubset(prompt_types):
        return None

    focus = projection.get("today_focus") if isinstance(projection.get("today_focus"), dict) else {}
    concept_label = _first_focus_topic_label(
        _projection_intent_value(prompts, "concept_label"),
        _projection_intent_value([focus], "concept_label"),
        _topic_from_focus_title(str(focus.get("title") or "")),
        _topic_from_prompt_text(str(prompts[0].get("text") or "")) if prompts else "",
    )
    error_label = _first_focus_topic_label(
        _projection_intent_value(prompts, "error_label"),
        _projection_intent_value([focus], "error_label"),
    )
    if not concept_label:
        return None

    generated_at = _parse_time(str(projection.get("generated_at") or ""))
    upgraded = build_home_personalization_projection_from_learning_signal(
        {
            "subject_id": _projection_intent_value(prompts + [focus], "subject_id"),
            "concept": {
                "label": concept_label,
                "taxonomy_code": _projection_intent_value(prompts + [focus], "taxonomy_code"),
            },
            "error": {"label": error_label},
            "training_intent_id": _projection_intent_value(prompts + [focus], "training_intent_id"),
            "evidence_refs": _projection_evidence_refs(prompts + [focus]),
            "learning_state_ref": _projection_intent_value(prompts + [focus], "learning_state_ref"),
            "suggested_mode": _projection_intent_value(prompts + [focus], "suggested_mode"),
        },
        generated_at=generated_at,
    )
    if not upgraded:
        return None
    source_status = dict(projection.get("source_status") or {})
    source_status.setdefault("fallback_used", False)
    source_status.setdefault("learning_report", "projection")
    source_status["upgraded_from"] = "legacy_home_projection"
    upgraded["source_status"] = source_status
    return upgraded


def _projection_intent_value(items: list[dict[str, Any]], key: str) -> str:
    for item in items:
        if not isinstance(item, dict):
            continue
        for source in (
            item.get("intent"),
            item.get("prompt_intent"),
            item,
        ):
            if not isinstance(source, dict):
                continue
            text = str(source.get(key) or "").strip()
            if text:
                return text
    return ""


def _explicit_concept_label(payload: dict[str, Any]) -> str:
    concept = payload.get("concept") if isinstance(payload.get("concept"), dict) else {}
    for value in (concept.get("label"), concept.get("name")):
        text = normalize_learning_topic_text(value)
        if text:
            return text
    return ""


def _projection_evidence_refs(items: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for source in (item.get("intent"), item.get("prompt_intent"), item):
            if not isinstance(source, dict):
                continue
            for value in list(source.get("evidence_refs") or []):
                text = str(value or "").strip()
                if text and text not in refs:
                    refs.append(text)
    return refs[:5]


def _topic_from_focus_title(value: str) -> str:
    text = str(value or "").strip()
    for prefix in ("今日焦点：", "今日焦点:"):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _topic_from_prompt_text(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("用 3 道题训练"):
        return text.replace("用 3 道题训练", "", 1).strip()
    if text.startswith("复盘") and "里的" in text:
        return text.replace("复盘", "", 1).split("里的", 1)[0].strip()
    if text.startswith("讲清楚") and text.endswith("的关键判断"):
        return text.replace("讲清楚", "", 1).removesuffix("的关键判断").strip()
    return ""


def _valid_focus(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    title = str(value.get("title") or "").strip()
    if not title:
        return False
    topic = _topic_from_focus_title(title)
    if not topic or not normalize_home_focus_topic_label(topic):
        return False
    canonical_topic = canonical_learning_topic_label(topic)
    if not canonical_topic:
        return False
    intent = value.get("intent") if isinstance(value.get("intent"), dict) else {}
    concept_label = str(intent.get("concept_label") or "").strip()
    if concept_label:
        intent_topic = canonical_learning_topic_label(concept_label)
        if intent_topic != canonical_topic:
            return False
    return True


def _valid_prompts(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            return False
        intent = item.get("intent") if isinstance(item.get("intent"), dict) else None
        if not isinstance(intent, dict):
            return False
        concept_label = str(intent.get("concept_label") or "").strip()
        if not concept_label:
            return False
        canonical_topic = canonical_learning_topic_label(concept_label)
        if not canonical_topic:
            return False
        prompt_type = str(item.get("prompt_type") or "").strip()
        if not _valid_prompt_text_for_topic(
            prompt_type=prompt_type,
            text=str(item.get("text") or "").strip(),
            topic=canonical_topic,
        ):
            return False
    return True


def _valid_focus_prompt_link(focus: Any, prompts: Any) -> bool:
    if not isinstance(focus, dict) or not isinstance(prompts, list) or not prompts:
        return False
    prompt = str(focus.get("prompt") or "").strip()
    if not prompt:
        return True
    first_prompt = prompts[0] if isinstance(prompts[0], dict) else {}
    return prompt == str(first_prompt.get("text") or "").strip()


def _valid_prompt_text_for_topic(*, prompt_type: str, text: str, topic: str) -> bool:
    if not text or not topic:
        return False
    expected = {
        "practice_prompt": f"用 3 道题训练{topic}",
        "concept_explain": f"讲清楚{topic}的关键判断",
        "exam_transfer": f"用一道真题场景理解{topic}",
        "knowledge_map": f"梳理{topic}的高频考点",
        "quick_check": f"用 1 个小问题验证{topic}是否真会了",
        "assessment": f"再测一次{topic}",
    }
    if prompt_type in expected:
        return text == expected[prompt_type]
    if prompt_type == "mistake_review":
        prefix = f"复盘{topic}里的"
        return text.startswith(prefix) and bool(text[len(prefix):].strip())
    return False


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
        focus = {"title": "先做一题，生成第一份学习证据", "meta": "starter"}
    title = str(focus.get("title") or "").strip()
    if "给系统" in title:
        focus["title"] = title.replace("给系统", "生成")
    focus["meta"] = "生成学情基线"
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


def _projection_from_recent_learning_events(
    events: list[dict[str, Any]] | None,
    *,
    generated_at: datetime,
) -> dict[str, Any] | None:
    for event in reversed(list(events or [])):
        payload = _payload_from_event(event)
        if str(payload.get("event_type") or "") != "learning_evidence":
            continue
        if not str(payload.get("event_id") or "").strip():
            event_id = _event_field(event, "event_id")
            if event_id:
                payload["event_id"] = event_id
        projection = build_home_personalization_projection_from_learning_signal(
            payload,
            generated_at=generated_at,
        )
        if projection:
            return projection
    return None


def _payload_from_event(event: Any) -> dict[str, Any]:
    payload: Any = {}
    if isinstance(event, dict):
        payload = event.get("payload_json") or event.get("payload") or {}
    else:
        payload = getattr(event, "payload_json", None) or getattr(event, "payload", None) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _event_field(event: Any, key: str) -> str:
    if isinstance(event, dict):
        return str(event.get(key) or "").strip()
    return str(getattr(event, key, "") or "").strip()


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
            "taxonomy_code": str(intent.get("taxonomy_code") or "").strip(),
            "taxonomy_id": str(intent.get("taxonomy_id") or "").strip(),
            "topic_id": str(intent.get("topic_id") or "").strip(),
            "topic_source": str(intent.get("topic_source") or "").strip(),
            "topic_confidence": str(intent.get("topic_confidence") or "").strip(),
        },
    }


def _assessment_retest_prompt(*, text: str, intent: dict[str, Any]) -> dict[str, Any]:
    evidence_refs = _normalize_refs(intent.get("evidence_refs"))
    concept_label = str(intent.get("concept_label") or "").strip()
    error_label = str(intent.get("error_label") or "").strip()
    return {
        "prompt_type": "assessment",
        "text": text,
        "evidence_refs": evidence_refs,
        "learning_state_ref": str(intent.get("learning_state_ref") or "").strip(),
        "suggested_mode": str(intent.get("suggested_mode") or "").strip(),
        "intent": {
            "source": "learner_state.home_personalization",
            "reason": str(intent.get("reason") or "training_completion_retest"),
            "learning_signal_type": "assessment",
            "action_mode": "assessment",
            "assessment_type": "topic_diagnostic",
            "subject_id": str(intent.get("subject_id") or "").strip(),
            "concept_label": concept_label,
            "error_label": error_label,
            "evidence_refs": evidence_refs,
            "taxonomy_code": str(intent.get("taxonomy_code") or "").strip(),
            "taxonomy_id": str(intent.get("taxonomy_id") or "").strip(),
            "topic_id": str(intent.get("topic_id") or "").strip(),
            "topic_source": str(intent.get("topic_source") or "").strip(),
            "topic_confidence": str(intent.get("topic_confidence") or "").strip(),
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
    for code in list(payload.get("error_codes") or []):
        label = str(code or "").strip()
        if label:
            return label
    return ""


def _first_focus_topic_label(*values: Any) -> str:
    for value in values:
        text = normalize_home_focus_topic_label(value)
        if text:
            return text
    return ""


def normalize_home_focus_topic_label(value: Any) -> str:
    return normalize_learning_topic_text(value)


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
    "normalize_home_focus_topic_label",
    "write_home_personalization_projection",
]
