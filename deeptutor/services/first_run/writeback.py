from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from deeptutor.services.first_run import manifest as manifest_module
from deeptutor.services.first_run.prescription_resolver import (
    resolve_first_run_prescription,
)
from deeptutor.services.learner_state.home_personalization import (
    build_home_personalization_projection_from_learning_signal,
    write_home_personalization_projection,
)
from deeptutor.services.learner_state.progress_counters import (
    write_progress_counters,
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
        prescription = resolve_first_run_prescription(scored)
        focus_item = dict(prescription["focus_item"])
        target_pack_id = str(prescription["target_pack_id"] or "").strip().upper()
        provisional_intent = build_learning_training_intent(
            user_id=normalized_user_id,
            concept_id=str(focus_item["concept_id"]),
            concept_label=str(focus_item["concept_label"]),
            evidence_refs=[],
            source=SOURCE_FEATURE,
            reason="first_run_first_missed_item" if missed else "first_run_clean_baseline",
            training_mode="mixed_review",
            target_pack_id=target_pack_id,
        )

        events: list[Any] = []
        for item in scored:
            is_focus = item["question_id"] == focus_item["question_id"]
            is_correct = bool(item["is_correct"])
            error_events = [] if is_correct else [{
                "error_code": "unknown_error",
                "concept_tag": item["concept_id"],
                "diagnosis": "首次摸底未命中，等待后续练习确认",
            }]
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
                "is_correct": is_correct,
                "duration_ms": int(item["duration_ms"]),
                "score_awarded": 1.0 if is_correct else 0.0,
                "max_score": 1.0,
                "knowledge_points": [item["concept_label"]],
                "concept_id": item["concept_id"],
                "concept_label": item["concept_label"],
                "node_code": item["concept_id"],
                "taxonomy_code": item["concept_id"],
                "error_codes": [] if is_correct else ["unknown_error"],
                "error_events": error_events,
                "quality": {"evidence_level": "L0_observed"},
                "next_training_signal": {
                    "concept": item["concept_id"],
                    "concept_label": item["concept_label"],
                    "error_code": "unknown_error" if not is_correct else "",
                },
                "measurement_confidence": "low_first_run_static_mcq",
                "training_intent_id": provisional_intent["training_intent_id"] if is_focus else "",
                "target_pack_id": target_pack_id if is_focus else "",
                "target_pack_refs": list(prescription["mapping_refs"]) if is_focus else [],
                "prescription_phase": "assigned" if is_focus else "",
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
        focus_event_ids = [
            event_ids[index]
            for index, item in enumerate(scored)
            if item["question_id"] == focus_item["question_id"]
        ]
        training_intent = build_learning_training_intent(
            user_id=normalized_user_id,
            concept_id=str(focus_item["concept_id"]),
            concept_label=str(focus_item["concept_label"]),
            evidence_refs=focus_event_ids,
            source=SOURCE_FEATURE,
            reason="first_run_first_missed_item" if missed else "first_run_clean_baseline",
            training_mode="mixed_review",
            target_pack_id=target_pack_id,
        )
        home_projection = self._write_home_projection(
            user_id=normalized_user_id,
            focus_item=focus_item,
            event_ids=focus_event_ids,
            training_intent=training_intent,
            generated_at=generated_at,
            missed=bool(missed),
        )
        self._write_explicit_preferences(
            user_id=normalized_user_id,
            preferences=preferences,
            script_version=canonical_request["script_version"],
            completed_at=canonical_request["completed_at"],
        )
        # 学习首页的三个数字（total_attempts / last_practiced_at / today_done）从
        # 证据账本派生回写 PROGRESS。放在 home projection 之后：projection 失败要
        # 整单不落地，而计数投影是尽力而为，不该反过来卡住已完成的摸底。
        progress_counters = write_progress_counters(
            self._learner_state,
            user_id=normalized_user_id,
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
            "progress_counters": progress_counters,
        }

    def _write_explicit_preferences(
        self,
        *,
        user_id: str,
        preferences: dict[str, str],
        script_version: str,
        completed_at: str,
    ) -> None:
        self._learner_state.merge_profile_strict(user_id, {
            "learning_preferences": {
                "first_run": {
                    **preferences,
                    "script_version": script_version,
                    "completed_at": completed_at,
                    "source": "explicit_first_run_v1",
                }
            }
        })

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
            "target_pack_id": str(training_intent.get("target_pack_id") or ""),
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
        projection["target_pack_id"] = str(training_intent.get("target_pack_id") or "")
        if not write_home_personalization_projection(
            self._learner_state,
            user_id=user_id,
            projection=projection,
        ):
            raise RuntimeError("first_run_home_projection_unavailable")
        return dict(projection or {})


__all__ = ["FirstRunIdempotencyConflict", "FirstRunWritebackService"]
