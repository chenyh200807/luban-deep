from __future__ import annotations

import logging
from typing import Any

from deeptutor.contracts.error_codes import check_emitted_error_codes
from deeptutor.contracts.bot_runtime_defaults import CONSTRUCTION_EXAM_BOT_DEFAULTS
from deeptutor.services.taxonomy.taxonomy_authority import (
    normalize_taxonomy_code,
    taxonomy_label,
)

logger = logging.getLogger(__name__)


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
        blueprint_version: str = "",
    ) -> dict[str, Any]:
        # Lazy import: learner_state's package __init__ transitively imports
        # member_console, which imports this module — a module-level import here
        # deadlocks standalone imports of writeback (pre-existing latent cycle).
        from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

        items = [dict(item) for item in list(scored_result.get("items") or [])]
        all_codes = [code for item in items for code in list(item.get("error_codes") or [])]
        check_emitted_error_codes(all_codes)
        # 过线体检 §7.1/§7.3: when the blueprint declares an item→dimension
        # binding, evidence events additionally carry the ability dimension and
        # per-scoring-point observations with CANONICAL registry error codes.
        # Display buckets are a read-model projection and are never persisted.
        dimension_by_section: dict[str, str] = {}
        if blueprint_version:
            try:
                from deeptutor.services.assessment.blueprint import ability_dimensions_by_section

                dimension_by_section = ability_dimensions_by_section(blueprint_version)
            except ValueError:
                dimension_by_section = {}
        learning_event_refs: list[dict[str, Any]] = []
        mistake_book_refs: list[dict[str, Any]] = []
        home_projection_payload: dict[str, Any] | None = None
        home_projection_is_correct = True
        bot_id = CONSTRUCTION_EXAM_BOT_DEFAULTS.bot_ids[0]
        discarded_node_codes = 0
        failed_item_count = 0
        for item in items:
            try:
                question_id = str(item.get("question_id") or "").strip()
                knowledge_points = list(item.get("knowledge_points") or [])
                concept_id = _assessment_concept_id(item=item, knowledge_points=knowledge_points)
                error_codes = list(item.get("error_codes") or [])
                is_correct = bool(item.get("is_correct"))
                payload_json = {
                    "event_type": "learning_evidence",
                    "assessment_type": assessment_type,
                    "quiz_id": quiz_id,
                    "form_id": form_id,
                    "question_id": question_id,
                    "source_question_id": item.get("source_question_id"),
                    "learner_answer": item.get("learner_answer"),
                    "correct_answer": item.get("correct_answer"),
                    "is_correct": is_correct,
                    "knowledge_points": knowledge_points,
                    "concept_id": concept_id,
                    "error_codes": error_codes,
                    "error_events": [
                        {
                            "error_code": code,
                            "concept_tag": concept_id,
                        }
                        for code in error_codes
                    ],
                    "measurement_confidence": item.get("measurement_confidence"),
                    "simple_explanation": item.get("simple_explanation"),
                }
                ability_dimension = dimension_by_section.get(str(item.get("section_id") or ""), "")
                if ability_dimension:
                    payload_json["ability_dimension"] = ability_dimension
                    payload_json["scoring_point_observations"] = [
                        {
                            "scoring_point": str(point or "").strip(),
                            "observed": "correct" if is_correct else "incorrect",
                            "error_codes": error_codes,
                        }
                        for point in (knowledge_points or ["综合能力"])
                        if str(point or "").strip()
                    ]
                # §6-6：normalize 只做形态归一不校验存在性，自由中文串曾照落
                # node_code 污染 taxonomy join。写入侧收口：只有 resolver 真能
                # 解析的 code 才允许写 node_code/taxonomy_code。
                taxonomy_code = normalize_taxonomy_code(concept_id)
                if taxonomy_code and taxonomy_label(taxonomy_code):
                    payload_json["node_code"] = taxonomy_code
                    payload_json["taxonomy_code"] = taxonomy_code
                else:
                    discarded_node_codes += 1
                payload_json["typed_edges"] = _typed_edges_from_assessment_item(
                    question_id=question_id,
                    submission_id=f"{quiz_id}:{question_id}",
                    concept_id=concept_id,
                    error_codes=error_codes,
                    source_feature="assessment_testset",
                )
                event = self._learner_state_service.append_memory_event(
                    user_id,
                    source_feature="assessment_testset",
                    source_id=f"{quiz_id}:{question_id}",
                    source_bot_id=bot_id,
                    memory_kind="learning_evidence",
                    payload_json=payload_json,
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
                if knowledge_points and (home_projection_payload is None or (home_projection_is_correct and not is_correct)):
                    home_projection_payload = _home_projection_payload_from_assessment_item(
                        payload_json,
                        subject_id=subject_id,
                        event_id=str(event.event_id),
                        attempt_ref=attempt_ref,
                    )
                    home_projection_is_correct = is_correct
                if not is_correct:
                    saved = self._mistake_book_service.save_item(
                        user_id=user_id,
                        attempt_ref=attempt_ref,
                        subject_id=subject_id,
                        bot_id=bot_id,
                        title=str(item.get("question_stem") or item.get("source_question_id") or question_id),
                        concept_label=(knowledge_points or ["综合能力"])[0],
                        error_label="、".join(error_codes) or "未归因错误",
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
            except Exception:
                # 单题失败不再杀死整卷回写(2026-08-07 审计:曾 3/30 写入即中止,
                # 后 27 题全部丢失)。逐题隔离+显式留痕;dedupe_key 幂等保证补写安全。
                failed_item_count += 1
                logger.exception(
                    "assessment writeback item failed: user_id=%s quiz_id=%s question_id=%s",
                    user_id,
                    quiz_id,
                    str(item.get("question_id") or ""),
                )
        if discarded_node_codes:
            # 病H-3 可观测性:resolver 解析不了的 concept_id 不写 node_code
            # (写入侧收口不变)——按次汇总一行 info,不逐条 warning 刷屏。
            logger.info(
                "assessment writeback dropped %s unresolvable node_code(s): user_id=%s quiz_id=%s",
                discarded_node_codes,
                user_id,
                quiz_id,
            )
        _write_home_projection(
            learner_state_service=self._learner_state_service,
            user_id=user_id,
            payload_json=home_projection_payload,
        )
        return {
            "learning_event_refs": learning_event_refs,
            "mistake_book_refs": mistake_book_refs,
            "failed_item_count": failed_item_count,
            "writeback_status": {
                "learning_event_count": len(learning_event_refs),
                "mistake_book_count": len(mistake_book_refs),
                "failed_item_count": failed_item_count,
            },
        }


def _assessment_concept_id(*, item: dict[str, Any], knowledge_points: list[Any]) -> str:
    provenance = dict(item.get("provenance") or {})
    for value in (
        item.get("concept_id"),
        item.get("node_code"),
        item.get("knowledge_node_id"),
        item.get("section_id"),
        provenance.get("node_code"),
        (knowledge_points or ["综合能力"])[0],
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "综合能力"


def _typed_edges_from_assessment_item(
    *,
    question_id: str,
    submission_id: str,
    concept_id: str,
    error_codes: list[str],
    source_feature: str,
) -> list[dict[str, Any]]:
    question = str(question_id or "").strip()
    submission = str(submission_id or "").strip() or question
    concept = str(concept_id or "").strip()
    edges: list[dict[str, Any]] = []
    if question and concept:
        edges.append(_edge("question_tests_concept", "question", question, "concept", concept, source_feature))
    if submission and question:
        edges.append(_edge("submission_answered_question", "submission", submission, "question", question, source_feature))
    for raw_code in list(error_codes or []):
        code = str(raw_code or "").strip()
        if not code:
            continue
        error_id = f"{concept}:{code}" if concept else code
        if submission:
            edges.append(_edge("submission_triggered_error", "submission", submission, "error", error_id, source_feature))
        training_id = f"{source_feature}:{concept}:{code}:review" if concept else f"{source_feature}:{code}:review"
        edges.append(_edge("error_points_to_training", "error", error_id, "next_training", training_id, source_feature))
    return _dedupe_edges(edges)


def _edge(
    edge_type: str,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    source_feature: str,
) -> dict[str, Any]:
    return {
        "edge_type": edge_type,
        "from": {"type": from_type, "id": from_id},
        "to": {"type": to_type, "id": to_id},
        "source_feature": source_feature,
        "confidence": 0.8,
    }


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for edge in edges:
        key = (
            str(edge.get("edge_type") or ""),
            str((edge.get("from") or {}).get("id") or ""),
            str((edge.get("to") or {}).get("id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _home_projection_payload_from_assessment_item(
    payload_json: dict[str, Any],
    *,
    subject_id: str,
    event_id: str,
    attempt_ref: str,
) -> dict[str, Any]:
    knowledge_points = list(payload_json.get("knowledge_points") or [])
    error_codes = list(payload_json.get("error_codes") or [])
    concept_label = str((knowledge_points or ["综合能力"])[0] or "").strip()
    error_label = "、".join(str(code or "").strip() for code in error_codes if str(code or "").strip())
    projection_payload = dict(payload_json)
    projection_payload.update(
        {
            "subject_id": subject_id,
            "concept": {"label": concept_label},
            "event_id": event_id,
            "attempt_ref": attempt_ref,
            "evidence_refs": [ref for ref in (event_id, attempt_ref) if ref],
            "suggested_mode": "deep" if error_label else "smart",
        }
    )
    if error_label:
        projection_payload["error"] = {"label": error_label}
    return projection_payload


def _write_home_projection(
    *,
    learner_state_service: Any,
    user_id: str,
    payload_json: dict[str, Any] | None,
) -> None:
    if not isinstance(payload_json, dict):
        return
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
        # Best-effort, but never silent: a swallowed failure here degrades the home
        # personalization with no operational signal. Log so a systemic failure is visible.
        logger.warning("home personalization projection write failed: user_id=%s", user_id, exc_info=True)
        return
