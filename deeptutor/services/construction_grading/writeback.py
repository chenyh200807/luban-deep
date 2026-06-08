from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref


logger = logging.getLogger(__name__)


def write_grading_error_events(
    *,
    learner_state_service: Any,
    user_id: str,
    grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any],
    source_id: str,
    source_bot_id: str | None = None,
    include_success_events: bool = False,
    training_intent_id: str | None = None,
    prescription_phase: str | None = None,
    prescription_result: dict[str, Any] | None = None,
    mistake_book_service: Any | None = None,
) -> int:
    """Write grading error events through the existing LearnerStateService authority."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return 0
    if isinstance(grading_result, dict) and grading_result.get("type") == "batch":
        count = 0
        for index, item in enumerate(list(grading_result.get("items") or []), 1):
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("question_id") or f"item-{index}").strip()
            count += write_grading_error_events(
                learner_state_service=learner_state_service,
                user_id=normalized_user_id,
                grading_result=item,
                source_id=f"{source_id}:{question_id}",
                source_bot_id=source_bot_id,
                include_success_events=include_success_events,
                training_intent_id=training_intent_id,
                prescription_phase=prescription_phase,
                prescription_result=prescription_result,
                mistake_book_service=mistake_book_service,
            )
        return count

    payload_json = build_learning_evidence_payload(
        grading_result=grading_result,
        turn_id=source_id,
    )
    if training_intent_id:
        payload_json["training_intent_id"] = str(training_intent_id or "").strip()
    phase = str(prescription_phase or "").strip()
    if phase:
        payload_json["prescription_phase"] = phase
    result = _prescription_result_payload(prescription_result)
    if result:
        payload_json["prescription_result"] = result
    if not payload_json["quality"]["writeback_eligible"]:
        if not include_success_events or not _is_success_learning_evidence(payload_json):
            return 0
        payload_json["quality"] = {
            **dict(payload_json.get("quality") or {}),
            "writeback_eligible": True,
            "writeback_reason": "success_improvement_signal",
        }
    if not payload_json["quality"]["writeback_eligible"]:
        return 0
    dedupe_key = build_learning_evidence_dedupe_key(
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    event = learner_state_service.append_memory_event(
        normalized_user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind="learning_evidence",
        payload_json=payload_json,
        dedupe_key=dedupe_key,
    )
    _write_mistake_book_item(
        mistake_book_service=mistake_book_service,
        user_id=normalized_user_id,
        event_id=str(getattr(event, "event_id", "") or ""),
        source_bot_id=source_bot_id,
        payload_json=payload_json,
    )
    _write_home_projection(
        learner_state_service=learner_state_service,
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    return 1


def write_case_grading_event_learning_evidence(
    *,
    learner_state_service: Any,
    user_id: str,
    grading_event: dict[str, Any],
    source_id: str,
    source_bot_id: str | None = None,
    user_answer: str = "",
    question_stem: str = "",
    node_code: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Persist a V1 ``case_grading_completed`` event as canonical learning_evidence.

    The raw grading event remains the scoring authority. The long-term memory stream
    receives one append-only learning_evidence payload that points back to that event;
    Learning Brain may observe it immediately, but candidate/open-world evidence is not
    promoted into stable mastery here.
    """
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {"writeback_count": 0, "reason": "missing_user_id"}
    if not isinstance(grading_event, dict) or grading_event.get("event_type") != "case_grading_completed":
        return {"writeback_count": 0, "reason": "not_case_grading_completed"}
    try:
        from deeptutor.services.construction_grading import rubric_grader_v1 as _G

        payload_json = _G.to_learning_evidence(grading_event, node_code=node_code)
    except Exception as exc:  # noqa: BLE001 — writeback must fail closed
        logger.warning("case grading event learning-evidence projection failed: %s", exc, exc_info=True)
        return {"writeback_count": 0, "reason": "projection_failed"}

    payload_json.update({
        "schema_version": 1,
        "legacy_event_type": "case_grading_completed",
        "source": "construction_grading",
        "turn_id": str(source_id or "").strip(),
        "session_id": str(session_id or "").strip(),
        "user_answer": str(user_answer or "").strip(),
        "question_stem": str(question_stem or "").strip(),
        "grading_event": dict(grading_event),
        "preview_only": True,
        "claim_promotion_allowed": False,
        "mastery_raised": False,
        "canonical_truth_written": False,
        "quality": {
            "writeback_eligible": True,
            "writeback_reason": "case_grading_completed_v1",
            "evidence_level": "L0_observed",
        },
    })
    dedupe_key = build_learning_evidence_dedupe_key(
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    event = learner_state_service.append_memory_event(
        normalized_user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind="learning_evidence",
        payload_json=payload_json,
        dedupe_key=dedupe_key,
    )
    return {
        "writeback_count": 1,
        "event_id": str(getattr(event, "event_id", "") or ""),
        "dedupe_key": dedupe_key,
        "learning_evidence_payload": payload_json,
    }


def _prescription_result_payload(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    status = str(value.get("status") or "").strip()
    if status:
        result["status"] = status
    if value.get("score_ratio") is not None:
        try:
            result["score_ratio"] = float(value.get("score_ratio") or 0)
        except (TypeError, ValueError):
            pass
    verified_at = str(value.get("verified_at") or "").strip()
    if verified_at:
        result["verified_at"] = verified_at
    return result


def _is_success_learning_evidence(payload_json: dict[str, Any]) -> bool:
    if payload_json.get("error_events") or payload_json.get("errors"):
        return False
    question_id = str(payload_json.get("question_id") or "").strip()
    signal = payload_json.get("next_training_signal") if isinstance(payload_json.get("next_training_signal"), dict) else {}
    concept = str((signal or {}).get("concept") or "").strip()
    try:
        score_awarded = float(payload_json.get("score_awarded") or 0)
        max_score = float(payload_json.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return bool(question_id and concept and max_score > 0 and score_awarded >= max_score)


def _write_mistake_book_item(
    *,
    mistake_book_service: Any | None,
    user_id: str,
    event_id: str,
    source_bot_id: str | None,
    payload_json: dict[str, Any],
) -> None:
    if not _is_mistake_book_candidate(payload_json):
        return
    normalized_event = str(event_id or "").strip()
    if not normalized_event:
        return
    service = mistake_book_service
    if service is None:
        try:
            from deeptutor.services.learner_state.mistake_book import MistakeBookService

            service = MistakeBookService()
        except Exception:
            return
    saver = getattr(service, "save_item", None)
    if not callable(saver):
        return
    try:
        saver(
            user_id=user_id,
            attempt_ref=sign_attempt_ref(
                user_id=user_id,
                event_id=normalized_event,
                question_id=str(payload_json.get("question_id") or "").strip(),
            ),
            subject_id=_mistake_book_subject_id(payload_json=payload_json, source_bot_id=source_bot_id),
            bot_id=str(source_bot_id or "").strip(),
            title=_mistake_book_title(payload_json),
            concept_label=_mistake_book_concept(payload_json),
            error_label=_mistake_book_error_label(payload_json),
            note=_mistake_book_note(payload_json),
            tags=_mistake_book_tags(payload_json),
        )
    except Exception as exc:
        logger.debug("mistake book auto-write skipped: %s", exc)


def _is_mistake_book_candidate(payload_json: dict[str, Any]) -> bool:
    if payload_json.get("error_events") or payload_json.get("errors"):
        return True
    try:
        score_awarded = float(payload_json.get("score_awarded") or 0)
        max_score = float(payload_json.get("max_score") or 0)
    except (TypeError, ValueError):
        return False
    return max_score > 0 and score_awarded < max_score


def _mistake_book_subject_id(*, payload_json: dict[str, Any], source_bot_id: str | None) -> str:
    subject_id = str(payload_json.get("subject_id") or "").strip()
    if subject_id:
        return subject_id
    bot_id = str(source_bot_id or "").strip()
    if bot_id == "construction-exam":
        return "construction_exam_1"
    return bot_id or "general"


def _mistake_book_title(payload_json: dict[str, Any]) -> str:
    return (
        str(payload_json.get("question_stem") or "").strip()
        or str(payload_json.get("question_id") or "").strip()
        or "错题"
    )[:300]


def _mistake_book_concept(payload_json: dict[str, Any]) -> str:
    signal = payload_json.get("next_training_signal") if isinstance(payload_json.get("next_training_signal"), dict) else {}
    errors = [error for error in list(payload_json.get("error_events") or payload_json.get("errors") or []) if isinstance(error, dict)]
    return (
        str((signal or {}).get("focus") or "").strip()
        or str((signal or {}).get("concept") or "").strip()
        or str(errors[0].get("concept_tag") if errors else "").strip()
        or "待归类知识点"
    )[:128]


def _mistake_book_error_label(payload_json: dict[str, Any]) -> str:
    errors = [error for error in list(payload_json.get("error_events") or payload_json.get("errors") or []) if isinstance(error, dict)]
    if errors:
        first = errors[0]
        return (
            str(first.get("diagnosis") or "").strip()
            or str(first.get("error_code") or "").strip()
            or "待归因错因"
        )[:128]
    return "得分未达标"


def _mistake_book_note(payload_json: dict[str, Any]) -> str:
    explanation = payload_json.get("explanation")
    if isinstance(explanation, dict):
        for key in ("summary", "why_wrong", "advice"):
            text = str(explanation.get(key) or "").strip()
            if text:
                return text[:500]
    return _mistake_book_error_label(payload_json)[:500]


def _mistake_book_tags(payload_json: dict[str, Any]) -> list[str]:
    tags = []
    for key in ("question_type", "grading_mode"):
        text = str(payload_json.get(key) or "").strip()
        if text:
            tags.append(text)
    return tags[:6]


def _write_home_projection(*, learner_state_service: Any, user_id: str, payload_json: dict[str, Any]) -> None:
    try:
        from deeptutor.services.learner_state.home_personalization import (
            build_home_personalization_projection_from_learning_signal,
            write_home_personalization_projection,
        )

        projection = build_home_personalization_projection_from_learning_signal(payload_json)
        write_home_personalization_projection(
            learner_state_service,
            user_id=user_id,
            projection=projection,
        )
    except Exception:
        return
