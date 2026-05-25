from __future__ import annotations

from typing import Any

from deeptutor.contracts.error_codes import check_emitted_error_codes
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref


class AssessmentWritebackService:
    def __init__(self, *, learner_state_service: Any, mistake_book_service: Any) -> None:
        self._learner_state_service = learner_state_service
        self._mistake_book_service = mistake_book_service

    def writeback(
        self,
        *,
        user_id: str,
        quiz_id: str,
        form_id: str,
        assessment_type: str,
        subject_id: str,
        scored_result: dict[str, Any],
    ) -> dict[str, Any]:
        items = [dict(item) for item in list(scored_result.get("items") or [])]
        all_codes = [code for item in items for code in list(item.get("error_codes") or [])]
        check_emitted_error_codes(all_codes)
        learning_event_refs: list[dict[str, Any]] = []
        mistake_book_refs: list[dict[str, Any]] = []
        bot_id = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
        for item in items:
            question_id = str(item.get("question_id") or "").strip()
            event = self._learner_state_service.append_memory_event(
                user_id,
                source_feature="assessment_testset",
                source_id=f"{quiz_id}:{question_id}",
                source_bot_id=bot_id,
                memory_kind="learning_evidence",
                payload_json={
                    "event_type": "learning_evidence",
                    "assessment_type": assessment_type,
                    "quiz_id": quiz_id,
                    "form_id": form_id,
                    "question_id": question_id,
                    "source_question_id": item.get("source_question_id"),
                    "learner_answer": item.get("learner_answer"),
                    "correct_answer": item.get("correct_answer"),
                    "is_correct": bool(item.get("is_correct")),
                    "knowledge_points": list(item.get("knowledge_points") or []),
                    "error_codes": list(item.get("error_codes") or []),
                    "error_events": [
                        {
                            "error_code": code,
                            "concept_tag": (list(item.get("knowledge_points") or []) or ["综合能力"])[0],
                        }
                        for code in list(item.get("error_codes") or [])
                    ],
                    "measurement_confidence": item.get("measurement_confidence"),
                    "simple_explanation": item.get("simple_explanation"),
                },
                dedupe_key=f"assessment_item:{user_id}:{quiz_id}:{question_id}",
            )
            attempt_ref = sign_attempt_ref(
                user_id=user_id,
                event_id=str(event.event_id),
                question_id=question_id,
            )
            ref = {
                "event_id": str(event.event_id),
                "question_id": question_id,
                "attempt_ref": attempt_ref,
                "kind": "learning_evidence",
            }
            learning_event_refs.append(ref)
            if not bool(item.get("is_correct")):
                saved = self._mistake_book_service.save_item(
                    user_id=user_id,
                    attempt_ref=attempt_ref,
                    subject_id=subject_id,
                    bot_id=bot_id,
                    title=str(item.get("question_stem") or item.get("source_question_id") or question_id),
                    concept_label=(list(item.get("knowledge_points") or []) or ["综合能力"])[0],
                    error_label="、".join(list(item.get("error_codes") or [])) or "未归因错误",
                    note=str(item.get("simple_explanation") or ""),
                    tags=["assessment_testset", assessment_type],
                )
                mistake_book_refs.append(
                    {
                        "event_id": saved.get("event_id"),
                        "question_id": saved.get("question_id"),
                        "attempt_ref": saved.get("attempt_ref"),
                    }
                )
        return {
            "learning_event_refs": learning_event_refs,
            "mistake_book_refs": mistake_book_refs,
            "writeback_status": {
                "learning_event_count": len(learning_event_refs),
                "mistake_book_count": len(mistake_book_refs),
            },
        }
