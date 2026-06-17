from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult
from deeptutor.services.construction_grading.learning_evidence import (
    _canonical_topic_from_payload,
    _canonical_topic_payload,
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)
from deeptutor.services.learner_state.memory_lifecycle import LIFECYCLE_STAGE_SHORT_TERM
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
        "memory_lifecycle_stage": LIFECYCLE_STAGE_SHORT_TERM,
        "quality": {
            "writeback_eligible": True,
            "writeback_reason": "case_grading_completed_v1",
            "evidence_level": "L0_observed",
        },
    })
    _attach_canonical_topic(payload_json, question_stem=question_stem, node_code=node_code)
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


def public_grading_to_brain_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """result_payload 的公开投影：只下发回执 + 展示级 next_best_action。

    聊天与练题两个入口共用此口径。

    personalization_context / learning_training_intent / NBA 的 intent、
    evidence_refs、training_intent_id 属于服务端内部权威数据，不进客户端
    metadata（与 wx ws-stream-pure.buildNextBestActionView 的端上投影同口径，
    在服务端就收口）。PCP 仍在服务端用于渲染个性化反馈，只是不随结果下发。"""
    if not isinstance(meta, dict) or not meta:
        return {}
    public: dict[str, Any] = {}
    for key in ("grading_to_brain_loop", "learning_evidence_event_id", "pgo_grading_to_brain"):
        if key in meta:
            public[key] = meta[key]
    action = meta.get("next_best_action")
    if isinstance(action, dict) and str(action.get("title") or "").strip():
        public["next_best_action"] = {
            "title": str(action.get("title") or "").strip(),
            "action_type": str(action.get("action_type") or "").strip(),
            "target": str(action.get("target") or "").strip(),
            "why_this_now": str(action.get("why_this_now") or "").strip(),
            "materials": [
                str(item or "").strip()
                for item in list(action.get("materials") or [])
                if str(item or "").strip()
            ],
            "success_measure": str(action.get("success_measure") or "").strip(),
            "prescription_authority": str(action.get("prescription_authority") or "").strip(),
        }
    return public


def record_pgo_shadow_to_brain(
    *,
    learner_state_service: Any,
    user_id: str,
    shadow_payload: dict[str, Any],
    source_id: str,
    source_bot_id: str | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    """Record review-only PGO point verdicts into the existing learning-evidence stream.

    This is the PGO same-attempt readback path: artifact_version -> point verdict ->
    learning_evidence -> scoring-point read model -> NextBestAction. It deliberately
    does not promote canonical learner truth and does not mint official scores.
    """
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {}
    if not isinstance(shadow_payload, dict) or shadow_payload.get("shadow_status") != "ok":
        return {}
    point_verdicts = shadow_payload.get("point_verdicts")
    runtime_points = shadow_payload.get("runtime_points")
    if not isinstance(point_verdicts, dict) or not isinstance(runtime_points, list):
        return {}
    scoring_points = _pgo_scoring_points(runtime_points)
    if not scoring_points:
        return {}
    scoring_point_hits = _pgo_scoring_point_hits(scoring_points, point_verdicts=point_verdicts)
    if not scoring_point_hits:
        return {}
    knowql_query = shadow_payload.get("knowql_query") if isinstance(shadow_payload.get("knowql_query"), dict) else {}
    artifact_version = str(
        knowql_query.get("artifact_version")
        or shadow_payload.get("artifact_version")
        or "case_rubric_scored_pgo"
    ).strip()
    question_id = str(shadow_payload.get("question_id") or "").strip()
    score = shadow_payload.get("score") if isinstance(shadow_payload.get("score"), dict) else {}
    payload_json: dict[str, Any] = {
        "schema_version": 1,
        "event_type": "learning_evidence",
        "legacy_event_type": "pgo_case_rubric_shadow",
        "source": "construction_grading",
        "evidence_source": "construction_grading",
        "learning_signal_type": "pgo_case_rubric_shadow",
        "turn_id": str(source_id or "").strip(),
        "session_id": str(session_id or "").strip(),
        "question_id": question_id,
        "question_type": "case",
        "student_id": str(shadow_payload.get("student_id") or "").strip(),
        "score_awarded": score.get("awarded_score"),
        "max_score": score.get("max_score"),
        "score_ratio": score.get("coverage"),
        "preview_only": True,
        "claim_promotion_allowed": False,
        "mastery_raised": False,
        "canonical_truth_written": False,
        "memory_lifecycle_stage": LIFECYCLE_STAGE_SHORT_TERM,
        "quality": {
            "writeback_eligible": True,
            "writeback_reason": "pgo_shadow_same_attempt",
            "evidence_level": "L0_observed",
        },
        "rubric": {
            "rubric_id": "case_rubric_scored_pgo",
            "artifact_version": artifact_version,
            "rubric_mode": "curated_rubric",
            "scoring_points": scoring_points,
            "scoring_point_hits": scoring_point_hits,
        },
        "pgo_shadow": {
            "authority": "luban_case_rubric_pgo_shadow",
            "artifact_version": artifact_version,
            "score_authority": str(score.get("score_authority") or "").strip(),
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "not_production_grade": True,
        },
    }
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
    event_id = str(getattr(event, "event_id", "") or "")
    readback = _pgo_readback_projection(
        learner_state_service=learner_state_service,
        user_id=normalized_user_id,
    )
    meta: dict[str, Any] = {
        "pgo_grading_to_brain": {
            "writeback_count": 1,
            "event_id": event_id,
            "memory_kind": "learning_evidence",
            "authority": "learner_memory_events.learning_evidence",
            "artifact_version": artifact_version,
            "canonical_truth_written": False,
            "claim_promotion_allowed": False,
            "scoring_point_map_readback": readback.get("scoring_point_map_readback") or {},
        },
        "pgo_learning_evidence_event_id": event_id,
    }
    next_best_action = readback.get("next_best_action")
    if isinstance(next_best_action, dict) and next_best_action:
        meta["pgo_grading_to_brain"]["next_best_action"] = next_best_action
    return meta


def record_case_grading_to_brain(
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
    include_personalization_projection: bool = True,
) -> dict[str, Any]:
    """Grading-to-Brain 的唯一 turn 侧 recorder seam。

    组合：learning_evidence writeback + training_intent 派生 + 画像读取
    （dream cycle compiled 缓存优先，miss 回退最近 50 条 dry-run 合成）+
    PersonalizationContextPack + next_best_action。聊天（TutorBot loop）与
    练题（deep_question）两个入口都只消费返回的 meta dict，不得各自再拼装
    ——单一组合权威。Fail-closed：任何一步失败都不影响可见批改结果。
    """
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {}
    # batch 合并事件按子题拆分写入：合并事件只用于渲染同源；证据流必须
    # 保留每个子题的独立身份（独立 dedupe / canonical_topic），否则两个
    # 不相关主题的错误会被压进同一条证据，污染长期画像聚合。
    grading_events = _split_batch_grading_event(grading_event)
    if not grading_events:
        return {}
    writebacks: list[dict[str, Any]] = []
    for sub_event in grading_events:
        sub_qid = str(sub_event.get("question_id") or "").strip()
        sub_source_id = (
            source_id
            if len(grading_events) == 1 or not sub_qid
            else f"{source_id}:{sub_qid}"
        )
        writeback = write_case_grading_event_learning_evidence(
            learner_state_service=learner_state_service,
            user_id=normalized_user_id,
            grading_event=sub_event,
            source_id=sub_source_id,
            source_bot_id=source_bot_id,
            user_answer=user_answer,
            question_stem=question_stem,
            node_code=node_code if len(grading_events) == 1 else "",
            session_id=session_id,
        )
        if isinstance(writeback, dict) and int(writeback.get("writeback_count") or 0):
            writebacks.append(writeback)
    if not writebacks:
        return {}
    event_ids = [str(item.get("event_id") or "") for item in writebacks]
    event_id = event_ids[0]
    meta: dict[str, Any] = {
        "grading_to_brain_loop": {
            "writeback_count": len(writebacks),
            "event_id": event_id,
            "event_ids": event_ids,
            "memory_kind": "learning_evidence",
            "authority": "learner_memory_events.learning_evidence",
        },
        "learning_evidence_event_id": event_id,
    }
    payload = (
        writebacks[0].get("learning_evidence_payload")
        if isinstance(writebacks[0].get("learning_evidence_payload"), dict)
        else {}
    )
    intent = _training_intent_from_evidence_payload(
        user_id=normalized_user_id,
        payload_json=payload,
        event_id=event_id,
    )
    if not intent:
        return meta
    meta["learning_training_intent"] = intent
    if not include_personalization_projection:
        return meta
    meta.update(build_case_grading_personalization_meta(
        learner_state_service=learner_state_service,
        user_id=normalized_user_id,
        learning_training_intent=intent,
        event_id=event_id,
    ))
    return meta


def build_case_grading_personalization_meta(
    *,
    learner_state_service: Any,
    user_id: str,
    learning_training_intent: dict[str, Any],
    event_id: str = "",
) -> dict[str, Any]:
    """Build the expensive display projection for a recorded case-grading evidence event.

    The append-only learning_evidence event is the durable authority. This helper only reads compiled
    learner truth / dry-run synthesis to produce PCP and next-best-action presentation metadata.
    """
    normalized_user_id = str(user_id or "").strip()
    intent = learning_training_intent if isinstance(learning_training_intent, dict) else {}
    if not normalized_user_id or not intent:
        return {}
    try:
        from deeptutor.services.learner_state.personalization_context import (
            build_personalization_context_pack,
        )

        # gbrain daemon 化：优先读 dream cycle 夜间巩固的 compiled 投影缓存；
        # cache miss 回退内联 dry-run（最近 50 条窗口）。命中缓存时 top_claims
        # 是上次巩固的长期画像，本 turn 即时信号由 intent/recent_events 承载。
        learning_brain = None
        read_cached = getattr(learner_state_service, "read_compiled_learning_truth", None)
        if callable(read_cached):
            try:
                cached = read_cached(normalized_user_id)
            except Exception:  # noqa: BLE001 — 缓存读失败必须落到回退路径
                cached = None
            if isinstance(cached, dict) and cached:
                learning_brain = cached
        if learning_brain is None and hasattr(learner_state_service, "synthesize_learning_truth"):
            synthesized = learner_state_service.synthesize_learning_truth(
                normalized_user_id,
                dry_run=True,
                event_limit=50,
            )
            learning_brain = synthesized.get("projection") if isinstance(synthesized, dict) else None
        pcp = build_personalization_context_pack(
            user_id=normalized_user_id,
            learning_brain=learning_brain,
            active_training_intent=intent,
            recent_events=[{"event_id": event_id}] if event_id else None,
        )
    except Exception:  # noqa: BLE001 — PCP 是投影；构建失败保留 writeback meta
        logger.warning("grading-to-brain PCP projection failed", exc_info=True)
        return {}
    meta: dict[str, Any] = {"personalization_context": pcp}
    actions = pcp.get("next_best_action_candidates") if isinstance(pcp, dict) else []
    if isinstance(actions, list) and actions:
        meta["next_best_action"] = dict(actions[0])
    return meta


def _pgo_scoring_points(runtime_points: list[Any]) -> list[dict[str, Any]]:
    scoring_points: list[dict[str, Any]] = []
    for point in runtime_points:
        if not isinstance(point, dict):
            continue
        point_id = str(point.get("point_id") or "").strip()
        if not point_id:
            continue
        scoring_points.append({
            "point_id": point_id,
            "label": point_id,
            "knowledge_node_id": "",
            "ability_dimension": str(point.get("sub_type") or "pgo_case_rubric").strip(),
        })
    return scoring_points


def _pgo_scoring_point_hits(
    scoring_points: list[dict[str, Any]],
    *,
    point_verdicts: dict[str, Any],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for point in scoring_points:
        point_id = str(point.get("point_id") or "").strip()
        verdict = str(point_verdicts.get(point_id) or "").strip().lower()
        if not verdict:
            continue
        is_hit = verdict == "hit"
        hits.append({
            "point_id": point_id,
            "hit": is_hit,
            "awarded_score": None,
            "error_code": "" if is_hit else "E02",
            "mistake_type": "" if is_hit else verdict,
            "miss_reason": "" if is_hit else verdict,
        })
    return hits


def _pgo_readback_projection(
    *,
    learner_state_service: Any,
    user_id: str,
) -> dict[str, Any]:
    try:
        from deeptutor.services.learner_state.next_best_action import build_next_best_actions
        from deeptutor.services.learner_state.scoring_point_map_read_model import (
            build_scoring_point_map_read_projection,
        )

        events = learner_state_service.list_memory_events(user_id)
        point_map = build_scoring_point_map_read_projection(events=events, user_id=user_id)
        items = list(point_map.get("items") or [])
        intents = [
            (item.get("next_action") or {}).get("intent")
            for item in items
            if isinstance((item.get("next_action") or {}).get("intent"), dict)
        ]
        actions = build_next_best_actions(user_id=user_id, training_intents=intents, max_actions=1)
        readback: dict[str, Any] = {
            "scoring_point_map_readback": {
                "authority": (point_map.get("source_status") or {}).get("authority"),
                "prescription_authority": (point_map.get("source_status") or {}).get("prescription_authority"),
                "items_count": len(items),
                "empty_state": point_map.get("empty_state") or "",
            }
        }
        if actions:
            action = dict(actions[0])
            readback["next_best_action"] = {
                "title": str(action.get("title") or "").strip(),
                "action_type": str(action.get("action_type") or "").strip(),
                "target": str(action.get("target") or "").strip(),
                "why_this_now": str(action.get("why_this_now") or "").strip(),
                "materials": [
                    str(item or "").strip()
                    for item in list(action.get("materials") or [])
                    if str(item or "").strip()
                ],
                "success_measure": str(action.get("success_measure") or "").strip(),
                "prescription_authority": str(action.get("prescription_authority") or "").strip(),
            }
        return readback
    except Exception:  # noqa: BLE001 — readback is projection-only; evidence write is enough
        logger.warning("PGO grading-to-brain readback projection failed", exc_info=True)
        return {
            "scoring_point_map_readback": {
                "authority": "learner_memory_events.learning_evidence",
                "items_count": 0,
                "empty_state": "projection_failed",
            }
        }


def _split_batch_grading_event(grading_event: dict[str, Any]) -> list[dict[str, Any]]:
    """合并 batch 事件携带完整子事件（items）时按子题拆分；普通单题事件原样返回。
    任何形状异常都退回单事件路径（fail-open，不丢证据）。"""
    if not isinstance(grading_event, dict) or grading_event.get("event_type") != "case_grading_completed":
        return [grading_event] if isinstance(grading_event, dict) else []
    items = grading_event.get("items")
    if not isinstance(items, list) or len(items) < 2:
        return [grading_event]
    sub_events = [
        item
        for item in items
        if isinstance(item, dict) and item.get("event_type") == "case_grading_completed"
    ]
    if len(sub_events) != len(items):
        return [grading_event]
    return sub_events


def _training_intent_from_evidence_payload(
    *,
    user_id: str,
    payload_json: dict[str, Any],
    event_id: str,
) -> dict[str, Any]:
    weak_points = payload_json.get("weak_points") if isinstance(payload_json, dict) else []
    first = next((item for item in list(weak_points or []) if isinstance(item, dict)), None)
    if not first:
        return {}
    # 开放世界：weak point 的 concept_id 按防污染设计为 None，
    # 概念归属用 resolver 产出的 canonical_topic 兜底（断点1）。
    topic = (
        payload_json.get("canonical_topic")
        if isinstance(payload_json.get("canonical_topic"), dict)
        else {}
    )
    concept_id = str(first.get("concept_id") or topic.get("taxonomy_code") or "").strip()
    concept_label = str(first.get("concept_label") or topic.get("label") or "").strip()
    try:
        from deeptutor.services.learner_state.training_intent import build_learning_training_intent

        return build_learning_training_intent(
            user_id=user_id,
            concept_id=concept_id,
            concept_label=concept_label,
            error_code=str(first.get("error_code") or "").strip(),
            error_label=str(first.get("policy_type") or first.get("error_code") or "").strip(),
            evidence_refs=[event_id] if event_id else [],
            training_mode="case_repair",
            source="grading_to_brain_loop",
            reason="case_grading_completed -> learner_memory_events.learning_evidence",
        )
    except Exception:  # noqa: BLE001
        logger.warning("grading-to-brain training_intent projection failed", exc_info=True)
        return {}


def _attach_canonical_topic(
    payload_json: dict[str, Any],
    *,
    question_stem: str,
    node_code: str,
) -> None:
    """开放世界沉淀的概念归属：经 taxonomy resolver 解析 canonical_topic
    （contracts/learner-state.md：canonical_topic 是 resolver 对证据的只读投影）。
    命中才写、不命中不写（fail-open 留 L0 observed，不臆造概念污染画像）。
    resolver 是唯一 taxonomy 权威的查询入口，这里不引入第二归属来源。"""
    if payload_json.get("canonical_topic"):
        return
    knowledge_points = [
        str(item.get("diagnosis") or "").strip()
        for item in list(payload_json.get("error_events") or [])
        if isinstance(item, dict) and str(item.get("diagnosis") or "").strip()
    ]
    try:
        topic = _canonical_topic_from_payload({
            "node_code": str(node_code or "").strip(),
            "question_stem": str(question_stem or "").strip(),
            "knowledge_points": knowledge_points,
        })
    except Exception:  # noqa: BLE001 — 概念归属失败不能阻断证据写入
        logger.warning("canonical topic resolution failed for case grading writeback", exc_info=True)
        return
    if topic:
        payload_json["canonical_topic"] = _canonical_topic_payload(topic)


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
