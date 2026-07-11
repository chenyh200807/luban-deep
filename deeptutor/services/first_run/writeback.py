from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from deeptutor.services.first_run import manifest as manifest_module
from deeptutor.services.learner_state.home_personalization import (
    build_home_personalization_projection_from_learning_signal,
    write_home_personalization_projection,
)
from deeptutor.services.learner_state.training_intent import (
    build_learning_training_intent,
)

SOURCE_FEATURE = "first_run_diagnostic"
_DECLARED_PREFERENCE_KEYS = (
    "exam_stage",
    "answer_style",
    "material_version",
    "memory_channel",
    "study_slot",
    "motivation",
)
_DECLARED_PREFERENCE_VALUES = {
    "exam_stage": frozenset({"first", "second", "veteran", "watch"}),
    "answer_style": frozenset({"blank", "nopoint", "slow", "fear"}),
    "material_version": frozenset({"y2026", "y2025", "older", "unknown"}),
    "memory_channel": frozenset({"A", "B", "C", "D"}),
    "study_slot": frozenset({"A", "B", "C", "D"}),
    "motivation": frozenset({"A", "B", "C", "D"}),
}


class FirstRunIdempotencyConflict(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_preferences(value: dict[str, Any] | None) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    normalized: dict[str, str] = {}
    for key in _DECLARED_PREFERENCE_KEYS:
        text = str(raw.get(key) or "").strip()
        if not text:
            continue
        if text not in _DECLARED_PREFERENCE_VALUES[key]:
            raise ValueError(f"invalid_declared_preference:{key}")
        normalized[key] = text
    return normalized


def _normalized_answers(value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = [
        {
            "question_id": str(item.get("question_id") or "").strip(),
            "selected_key": str(item.get("selected_key") or "").strip(),
            "duration_ms": item.get("duration_ms", 0),
        }
        for item in list(value or [])
        if isinstance(item, dict)
    ]
    return sorted(normalized, key=lambda item: item["question_id"])


def _completed_at(value: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_completed_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class FirstRunWritebackService:
    def __init__(self, *, learner_state_service: Any) -> None:
        self._learner_state = learner_state_service

    def complete(
        self,
        *,
        user_id: str,
        completion_id: str,
        script_version: str,
        completed_at: str,
        answers: list[dict[str, Any]],
        declared_preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_user_id = str(user_id or "").strip()
        normalized_completion_id = str(completion_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id_required")
        if not normalized_completion_id:
            raise ValueError("completion_id_required")
        generated_at = _completed_at(completed_at)
        normalized_answers = _normalized_answers(answers)
        preferences = _normalized_preferences(declared_preferences)
        canonical_request = {
            "completion_id": normalized_completion_id,
            "script_version": str(script_version or "").strip(),
            "completed_at": generated_at.astimezone(timezone.utc).isoformat(),
            "answers": normalized_answers,
            "declared_preferences": preferences,
        }
        request_hash = _request_hash(canonical_request)
        scored = manifest_module.score_first_run_answers(
            script_version=canonical_request["script_version"],
            answers=normalized_answers,
        )
        missed = [item for item in scored if not item["is_correct"]]
        focus_item = dict((missed or scored)[0])
        provisional_intent = build_learning_training_intent(
            user_id=normalized_user_id,
            concept_id=str(focus_item["concept_id"]),
            concept_label=str(focus_item["concept_label"]),
            evidence_refs=[],
            source=SOURCE_FEATURE,
            reason="first_run_first_missed_item" if missed else "first_run_clean_baseline",
            training_mode="mixed_review",
        )

        events: list[Any] = []
        for item in scored:
            payload = {
                "event_type": "learning_evidence",
                "evidence_source": SOURCE_FEATURE,
                "assessment_type": "first_run_diagnostic",
                "completion_id": normalized_completion_id,
                "script_version": canonical_request["script_version"],
                "request_hash": request_hash,
                "question_id": item["question_id"],
                "source_question_id": item["source_question_id"],
                "source_scoring_point_id": item["source_scoring_point_id"],
                "source_refs": list(item["source_refs"]),
                "content_sha256": item["content_sha256"],
                "learner_answer": item["learner_answer"],
                "correct_answer": item["correct_answer"],
                "is_correct": bool(item["is_correct"]),
                "duration_ms": int(item["duration_ms"]),
                "knowledge_points": [item["concept_label"]],
                "concept_id": item["concept_id"],
                "concept_label": item["concept_label"],
                "node_code": item["concept_id"],
                "taxonomy_code": item["concept_id"],
                "error_codes": [],
                "measurement_confidence": "low_first_run_static_mcq",
                "training_intent_id": provisional_intent["training_intent_id"],
                "prescription_phase": "assigned",
                "mastery_promotion_allowed": False,
                "official_score_allowed": False,
                "claim_promotion_allowed": False,
            }
            event = self._learner_state.append_memory_event(
                normalized_user_id,
                source_feature=SOURCE_FEATURE,
                source_id=f"{normalized_completion_id}:{item['question_id']}",
                memory_kind="learning_evidence",
                payload_json=payload,
                dedupe_key=(
                    f"first_run_item:{normalized_user_id}:"
                    f"{normalized_completion_id}:{item['question_id']}"
                ),
            )
            existing_hash = str(getattr(event, "payload_json", {}).get("request_hash") or "")
            if existing_hash != request_hash:
                raise FirstRunIdempotencyConflict(normalized_completion_id)
            events.append(event)

        event_ids = [str(getattr(event, "event_id", "") or "").strip() for event in events]
        training_intent = build_learning_training_intent(
            user_id=normalized_user_id,
            concept_id=str(focus_item["concept_id"]),
            concept_label=str(focus_item["concept_label"]),
            evidence_refs=event_ids,
            source=SOURCE_FEATURE,
            reason="first_run_first_missed_item" if missed else "first_run_clean_baseline",
            training_mode="mixed_review",
        )
        self._write_explicit_preferences(
            user_id=normalized_user_id,
            preferences=preferences,
            script_version=canonical_request["script_version"],
            completed_at=canonical_request["completed_at"],
        )
        home_projection = self._write_home_projection(
            user_id=normalized_user_id,
            focus_item=focus_item,
            event_ids=event_ids,
            training_intent=training_intent,
            generated_at=generated_at,
            missed=bool(missed),
        )
        return {
            "completion_id": normalized_completion_id,
            "script_version": canonical_request["script_version"],
            "sync_status": "synced",
            "score": {
                "correct_count": sum(1 for item in scored if item["is_correct"]),
                "question_count": len(scored),
            },
            "items": [
                {
                    "question_id": item["question_id"],
                    "is_correct": bool(item["is_correct"]),
                    "concept_id": item["concept_id"],
                    "concept_label": item["concept_label"],
                    "event_id": event_ids[index],
                }
                for index, item in enumerate(scored)
            ],
            "learning_event_refs": event_ids,
            "training_intent": training_intent,
            "home_projection": home_projection,
        }

    def _write_explicit_preferences(
        self,
        *,
        user_id: str,
        preferences: dict[str, str],
        script_version: str,
        completed_at: str,
    ) -> None:
        profile = deepcopy(self._learner_state.read_profile(user_id) or {})
        learning_preferences = dict(profile.get("learning_preferences") or {})
        learning_preferences["first_run"] = {
            **preferences,
            "script_version": script_version,
            "completed_at": completed_at,
            "source": "explicit_first_run_v1",
        }
        profile["learning_preferences"] = learning_preferences
        self._learner_state.write_profile_strict(user_id, profile)

    def _write_home_projection(
        self,
        *,
        user_id: str,
        focus_item: dict[str, Any],
        event_ids: list[str],
        training_intent: dict[str, Any],
        generated_at: datetime,
        missed: bool,
    ) -> dict[str, Any]:
        concept_label = str(focus_item["concept_label"])
        signal = {
            "subject_id": "construction_exam",
            "concept_id": focus_item["concept_id"],
            "concept_label": concept_label,
            "taxonomy_code": focus_item["concept_id"],
            "knowledge_points": [concept_label],
            "training_intent_id": training_intent["training_intent_id"],
            "evidence_refs": event_ids,
            "learning_state_ref": event_ids[0] if event_ids else "",
            "next_training_signal": {
                "concept_id": focus_item["concept_id"],
                "concept_label": concept_label,
            },
            "error": {"label": "首次摸底未命中"} if missed else {},
        }
        projection = build_home_personalization_projection_from_learning_signal(
            signal,
            generated_at=generated_at,
            llm_topic_inferer=lambda _text: None,
        )
        if not write_home_personalization_projection(
            self._learner_state,
            user_id=user_id,
            projection=projection,
        ):
            raise RuntimeError("first_run_home_projection_unavailable")
        return dict(projection or {})


__all__ = ["FirstRunIdempotencyConflict", "FirstRunWritebackService"]
