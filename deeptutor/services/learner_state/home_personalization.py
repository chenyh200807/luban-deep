from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from deeptutor.services.learner_state.training_intent import build_learning_training_intent
from deeptutor.services.taxonomy.learning_topic_resolver import (
    ResolvedLearningTopic,
    TopicInferer,
    infer_learning_topic_with_llm,
    normalize_learning_topic_text,
    resolve_learning_topic_from_payload,
)
from deeptutor.services.taxonomy.textbook_directory import resolve_canonical_option


_TZ = timezone(timedelta(hours=8))
_PROJECTION_TTL = timedelta(hours=6)
_SEED_ROOT = Path(__file__).resolve().parents[3] / "data" / "seed"
_HOME_PROJECTION_CONTRACT = "canonical_taxonomy_v1"
_HOME_PROJECTION_TOPIC_AUTHORITY = "learner_state.home_personalization.canonical_taxonomy"
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
    normalized_projection = _normalize_projection(projection) if isinstance(projection, dict) else None
    if _is_fresh_projection(normalized_projection, now=current_time):
        return normalized_projection
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
    if not is_canonical_home_personalization_projection(projection):
        return False
    generated_at = _parse_time(str(projection.get("generated_at") or ""))
    if generated_at is None:
        return False
    return now - generated_at <= _PROJECTION_TTL


def build_home_personalization_projection_from_learning_signal(
    payload: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    llm_topic_inferer: TopicInferer | None = infer_learning_topic_with_llm,
) -> dict[str, Any] | None:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    topic = resolve_learning_topic_from_payload(
        payload,
        llm_topic_inferer=llm_topic_inferer,
    )
    explicit_label = _explicit_concept_label(payload)
    fallback_label = _fallback_concept_label_from_payload(payload)
    concept_label = topic.label if topic is not None else explicit_label or fallback_label
    canonical_topic = _resolve_canonical_home_topic(concept_label, topic=topic)
    if canonical_topic is None:
        return None
    concept_label = canonical_topic.label
    topic_fields = canonical_topic.intent_fields()
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
        **topic_fields,
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
        "source_status": _canonical_projection_source_status(
            {"fallback_used": False, "learning_report": "projection"}
        ),
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
    normalized_projection = _normalize_projection(projection)
    if not is_canonical_home_personalization_projection(normalized_projection):
        return False
    merger = getattr(learner_state_service, "merge_progress", None)
    if not callable(merger):
        return False
    merger(str(user_id or "").strip(), {"home_personalization": normalized_projection})
    return True


def _normalize_projection(projection: dict[str, Any] | None) -> dict[str, Any]:
    payload = deepcopy(projection or {})
    if not _has_canonical_projection_source_status(payload.get("source_status")):
        return {}
    upgraded = _upgrade_legacy_home_projection(payload)
    if upgraded is not None:
        payload = upgraded
    source_status = dict(payload.get("source_status") or {})
    source_status.setdefault("fallback_used", False)
    source_status.setdefault("learning_report", "projection")
    payload["source_status"] = _canonical_projection_source_status(source_status)
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
    canonical_topic = _resolve_canonical_home_topic(concept_label)
    if canonical_topic is None:
        return None
    concept_label = canonical_topic.label

    generated_at = _parse_time(str(projection.get("generated_at") or "")) or datetime.now(tz=_TZ)
    base_intent = {
        **canonical_topic.intent_fields(),
        "concept_label": concept_label,
        "error_label": error_label or "薄弱点",
        "subject_id": _projection_intent_value(prompts + [focus], "subject_id"),
        "training_intent_id": _projection_intent_value(prompts + [focus], "training_intent_id"),
        "evidence_refs": _projection_evidence_refs(prompts + [focus]),
        "learning_state_ref": _projection_intent_value(prompts + [focus], "learning_state_ref"),
        "suggested_mode": _projection_intent_value(prompts + [focus], "suggested_mode"),
    }
    upgraded_prompts = [
        _projection_prompt(
            prompt_type="practice_prompt",
            text=f"用 3 道题训练{concept_label}",
            intent={**base_intent, "training_mode": "mixed_review", "reason": "home_projection_practice"},
        ),
        _projection_prompt(
            prompt_type="mistake_review",
            text=f"复盘{concept_label}里的{base_intent['error_label']}",
            intent={**base_intent, "training_mode": "mistake_repair", "reason": "home_projection_mistake"},
        ),
        _projection_prompt(
            prompt_type="concept_explain",
            text=f"讲清楚{concept_label}的关键判断",
            intent={**base_intent, "training_mode": "concept_explain", "reason": "home_projection_concept"},
        ),
        _projection_prompt(
            prompt_type="exam_transfer",
            text=f"用一道真题场景理解{concept_label}",
            intent={**base_intent, "training_mode": "case_repair", "reason": "home_projection_exam_transfer"},
        ),
        _projection_prompt(
            prompt_type="knowledge_map",
            text=f"梳理{concept_label}的高频考点",
            intent={**base_intent, "training_mode": "rubric_recall", "reason": "home_projection_knowledge_map"},
        ),
        _projection_prompt(
            prompt_type="quick_check",
            text=f"用 1 个小问题验证{concept_label}是否真会了",
            intent={**base_intent, "training_mode": "mcq_discrimination", "reason": "home_projection_quick_check"},
        ),
    ]
    source_status = dict(projection.get("source_status") or {})
    source_status.setdefault("fallback_used", False)
    source_status.setdefault("learning_report", "projection")
    source_status["upgraded_from"] = "legacy_home_projection"
    source_status = _canonical_projection_source_status(source_status)
    return {
        "generated_at": generated_at.isoformat(),
        "source_status": source_status,
        "today_focus": {
            "title": f"今日焦点：{concept_label}",
            "meta": "来自 learner_state.home_personalization",
            "prompt": upgraded_prompts[0]["text"],
            "intent": upgraded_prompts[0]["intent"],
        },
        "recommended_prompts": upgraded_prompts,
    }


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


def _fallback_concept_label_from_payload(payload: dict[str, Any]) -> str:
    signal = payload.get("next_training_signal") if isinstance(payload.get("next_training_signal"), dict) else {}
    for value in (
        _explicit_concept_label(payload),
        signal.get("focus"),
        signal.get("concept"),
        *list(payload.get("knowledge_points") or [])[:3],
    ):
        text = _first_focus_topic_label(value)
        canonical_text = canonical_home_focus_topic_label(text)
        if canonical_text:
            return canonical_text
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
    canonical_focus_topic = _resolve_canonical_home_topic(topic)
    if canonical_focus_topic is None:
        return False
    canonical_topic = canonical_focus_topic.label
    intent = value.get("intent") if isinstance(value.get("intent"), dict) else {}
    concept_label = str(intent.get("concept_label") or "").strip()
    if concept_label:
        intent_topic = _resolve_canonical_home_topic(concept_label)
        if intent_topic is None or intent_topic.label != canonical_topic:
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
        canonical_topic = _resolve_canonical_home_topic(concept_label)
        if canonical_topic is None:
            return False
        prompt_type = str(item.get("prompt_type") or "").strip()
        if not _valid_prompt_text_for_topic(
            prompt_type=prompt_type,
            text=str(item.get("text") or "").strip(),
            topic=canonical_topic.label,
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
        "source_status": _canonical_projection_source_status(
            {
                "fallback_used": True,
                "fallback_reason": fallback_reason,
                "learning_report": "stale",
            }
        ),
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
        # §2.1 显式拍板：看动画（lesson_viewed 学-evidence）不顶替 today_focus——
        # 学→练连续性由 home_next_step_projection 组合层显式做，不靠事件顶替。
        if str(payload.get("learning_signal_type") or "") == "lesson_viewed":
            continue
        if not str(payload.get("event_id") or "").strip():
            event_id = _event_field(event, "event_id")
            if event_id:
                payload["event_id"] = event_id
        projection = build_home_personalization_projection_from_learning_signal(
            payload,
            generated_at=generated_at,
            # A dashboard read may only project persisted evidence. Semantic
            # inference belongs to the evidence write path; replaying LLM
            # classification for every historical event makes GET latency and
            # truth depend on a second, non-persisted authority.
            llm_topic_inferer=None,
        )
        if is_canonical_home_personalization_projection(projection):
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


def _canonical_projection_source_status(value: dict[str, Any] | None = None) -> dict[str, Any]:
    source_status = dict(value or {})
    source_status["home_projection_contract"] = _HOME_PROJECTION_CONTRACT
    source_status["topic_authority"] = _HOME_PROJECTION_TOPIC_AUTHORITY
    return source_status


def _has_canonical_projection_source_status(value: Any) -> bool:
    source_status = value if isinstance(value, dict) else {}
    return (
        source_status.get("home_projection_contract") == _HOME_PROJECTION_CONTRACT
        and source_status.get("topic_authority") == _HOME_PROJECTION_TOPIC_AUTHORITY
    )


def is_canonical_home_personalization_projection(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    source_status = value.get("source_status") if isinstance(value.get("source_status"), dict) else {}
    if not _has_canonical_projection_source_status(source_status):
        return False
    if source_status.get("fallback_used") is not False:
        return False
    if not _valid_focus(value.get("today_focus")) or not _valid_prompts(value.get("recommended_prompts")):
        return False
    return _valid_focus_prompt_link(value.get("today_focus"), value.get("recommended_prompts"))


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


def canonical_home_focus_topic_label(value: Any) -> str:
    text = normalize_home_focus_topic_label(value)
    if not text:
        return ""
    option = resolve_canonical_option(text)
    if option:
        return str(option.get("name") or "").strip()
    topic = resolve_learning_topic_from_payload({"knowledge_points": [text]}, llm_topic_inferer=None)
    if topic:
        return topic.label
    return ""


def _resolve_canonical_home_topic(
    value: Any, *, topic: ResolvedLearningTopic | None = None
) -> ResolvedLearningTopic | None:
    text = normalize_home_focus_topic_label(value)
    if not text:
        return None
    if topic is not None:
        label = normalize_home_focus_topic_label(topic.label)
        if label:
            return ResolvedLearningTopic(
                label=label,
                source=topic.source,
                confidence=topic.confidence,
                taxonomy_code=topic.taxonomy_code,
                taxonomy_id=topic.taxonomy_id,
                topic_id=topic.topic_id,
            )
    resolved = resolve_learning_topic_from_payload({"knowledge_points": [text]}, llm_topic_inferer=None)
    if resolved:
        return resolved
    option = resolve_canonical_option(text)
    if option:
        code = str(option.get("code") or "").strip()
        return ResolvedLearningTopic(
            label=str(option.get("name") or "").strip(),
            source="canonical_option",
            confidence="high",
            taxonomy_code=code,
            taxonomy_id=code,
        )
    return None


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
    "canonical_home_focus_topic_label",
    "is_canonical_home_personalization_projection",
    "normalize_home_focus_topic_label",
    "write_home_personalization_projection",
]
