"""Materialize learner compiled truth as read-only retrieval documents."""

from __future__ import annotations

import re
from typing import Any


_DEFAULT_MAX_CHARS_PER_DOC = 700
_DEFAULT_MAX_TOTAL_CHARS = 2400
_PROMPT_LIKE_RE = re.compile(
    r"(?i)("
    r"ignore\s+(all\s+)?previous\s+instructions|"
    r"system\s+prompt|developer\s+message|tool\s+instruction|"
    r"<\s*/?\s*(system|developer|tool|thinking)[^>]*>|"
    r"请忽略[^。；;\n]*(指令|要求|规则)|"
    r"系统提示|开发者消息|工具调用"
    r")"
)
_PRIVATE_FIELD_RE = re.compile(
    r"(?i)("
    r"\b1[3-9]\d{9}\b|"
    r"(wallet|phone|mobile|membership|account[_\s-]?id)\s*[:=]\s*[\w@.+-]+"
    r")"
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_level_rank(level: str) -> int:
    order = {
        "L0_observed": 0,
        "L1_repeated": 1,
        "L2_confirmed": 2,
        "L3_mastery_signal": 3,
    }
    return order.get(_text(level), -1)


def _evidence_level_from_claim_status(status: Any) -> str:
    normalized = _text(status)
    return {
        "observed": "L0_observed",
        "repeated": "L1_repeated",
        "confirmed": "L2_confirmed",
    }.get(normalized, "")


def _sanitize_compiled_truth_text(value: Any, *, max_chars: int) -> tuple[str, int, bool]:
    raw = _text(value)
    if not raw:
        return "", 0, False
    redaction_count = 0
    clean_lines: list[str] = []
    for line in raw.splitlines():
        if _PROMPT_LIKE_RE.search(line):
            redaction_count += 1
            continue
        sanitized = _PRIVATE_FIELD_RE.sub("[redacted]", line)
        if sanitized != line:
            redaction_count += 1
        clean_lines.append(sanitized)
    clean = "\n".join(line.strip() for line in clean_lines if line.strip())
    truncated = len(clean) > max_chars
    if truncated:
        clean = clean[:max_chars].rstrip()
    heavily_sanitized = redaction_count >= 2 or (bool(raw) and len(clean) < len(raw) * 0.65)
    return clean, redaction_count, heavily_sanitized


def _is_stale_or_superseded(item: dict[str, Any]) -> bool:
    status = _text(item.get("status") or item.get("state")).lower()
    if status in {"stale", "superseded", "deprecated", "inactive"}:
        return True
    decay_state = _text(item.get("decay_state")).lower()
    if decay_state and decay_state not in {"active", "confirmed"}:
        return True
    if item.get("stale") is True:
        return True
    return bool(_as_list(item.get("superseded_by_event_ids")))


def _format_compiled_truth_doc(object_id: str, item: dict[str, Any], truth: str) -> str:
    timeline_refs = _as_list(item.get("timeline_refs") or item.get("evidence_refs"))
    supporting_event_ids = _as_list(item.get("supporting_event_ids"))
    lines = [
        "## 学习事实编译",
        truth,
        f"对象: {object_id}",
        f"证据等级: {_text(item.get('evidence_level')) or 'unclassified'}",
    ]
    if supporting_event_ids:
        lines.append("支持事件: " + "、".join(_text(event_id) for event_id in supporting_event_ids[:6] if _text(event_id)))
    for ref in timeline_refs[:4]:
        ref_obj = _as_dict(ref)
        label = _text(ref_obj.get("label") or ref_obj.get("event_id") or ref_obj.get("source_id"))
        observed_at = _text(ref_obj.get("observed_at"))
        if label or observed_at:
            lines.append("证据流: " + " ".join(part for part in [observed_at, label] if part))
    return "\n".join(line for line in lines if line)


def _format_weak_point_doc(
    *,
    concept_id: str,
    error_code: str,
    truth: str,
    item: dict[str, Any],
    graph_context: dict[str, Any],
) -> str:
    lines = [
        "## 学员弱点召回事实",
        truth,
        f"知识点: {concept_id}",
        f"错因: {error_code}",
        f"证据等级: {_text(item.get('evidence_level')) or 'unclassified'}",
    ]
    supporting_event_ids = [_text(event_id) for event_id in _as_list(item.get("supporting_event_ids")) if _text(event_id)]
    if supporting_event_ids:
        lines.append("支持事件: " + "、".join(supporting_event_ids[:6]))
    training_targets = [_text(item) for item in _as_list(graph_context.get("training_target_ids")) if _text(item)]
    question_ids = [_text(item) for item in _as_list(graph_context.get("question_ids")) if _text(item)]
    rubric_items = [_text(item) for item in _as_list(graph_context.get("rubric_item_ids")) if _text(item)]
    if training_targets or question_ids or rubric_items:
        lines.append(
            "图谱链: "
            + "；".join(
                part
                for part in [
                    f"question={','.join(question_ids[:4])}" if question_ids else "",
                    f"rubric={','.join(rubric_items[:4])}" if rubric_items else "",
                    f"next_training={','.join(training_targets[:4])}" if training_targets else "",
                ]
                if part
            )
        )
    training = item.get("recommended_training") if isinstance(item.get("recommended_training"), dict) else {}
    focus = _text(training.get("focus"))
    mode = _text(training.get("mode"))
    if focus or mode:
        lines.append("训练建议: " + "；".join(part for part in [focus, mode] if part))
    return "\n".join(line for line in lines if line)


def _node_id(edge: dict[str, Any], side: str) -> str:
    node = edge.get(side) if isinstance(edge.get(side), dict) else {}
    return _text(node.get("id"))


def _append_unique(items: list[str], value: Any) -> None:
    text = _text(value)
    if text and text not in items:
        items.append(text)


def _graph_edges(projection: dict[str, Any]) -> list[dict[str, Any]]:
    graph = projection.get("typed_graph") if isinstance(projection.get("typed_graph"), dict) else {}
    return [edge for edge in _as_list(graph.get("edges")) if isinstance(edge, dict)]


def _projection_with_personalization_claims(projection: dict[str, Any]) -> dict[str, Any]:
    top_claims = _as_list(projection.get("top_claims"))
    if not top_claims:
        return projection
    compiled_objects = dict(_as_dict(projection.get("compiled_objects") or projection.get("objects")))
    for raw_claim in top_claims:
        claim = _as_dict(raw_claim)
        claim_id = _text(claim.get("claim_id") or claim.get("object_id"))
        if not claim_id:
            continue
        evidence_refs = _as_list(claim.get("evidence_refs") or claim.get("supporting_event_ids"))
        if not evidence_refs:
            continue
        evidence_level = _text(claim.get("evidence_level")) or _evidence_level_from_claim_status(claim.get("claim_status"))
        compiled_objects[f"personalization:{claim_id}"] = {
            "object_type": _text(claim.get("object_type")) or "personalization_claim",
            "current_truth": claim.get("label") or claim.get("current_truth") or claim.get("claim"),
            "evidence_level": evidence_level,
            "supporting_event_ids": evidence_refs,
            "evidence_refs": evidence_refs,
            "claim_status": claim.get("claim_status"),
        }
    normalized = dict(projection)
    normalized["compiled_objects"] = compiled_objects
    normalized.setdefault("subject", _text(projection.get("source")) or "PersonalizationContextPack")
    return normalized


def _graph_context_for_weak_point(
    projection: dict[str, Any],
    *,
    concept_id: str,
    error_code: str,
    supporting_event_ids: list[Any],
) -> dict[str, Any]:
    concept = _text(concept_id)
    code = _text(error_code)
    error_id = f"{concept}:{code}" if concept and code else ""
    support_ids = {_text(item) for item in supporting_event_ids if _text(item)}
    question_ids: list[str] = []
    rubric_item_ids: list[str] = []
    error_ids: list[str] = []
    training_target_ids: list[str] = []
    evidence_event_ids: list[str] = []
    related_edges: list[dict[str, Any]] = []

    edges = _graph_edges(projection)
    for edge in edges:
        edge_type = _text(edge.get("edge_type"))
        event_id = _text(edge.get("evidence_event_id"))
        if edge_type == "question_tests_concept" and _node_id(edge, "to") == concept:
            _append_unique(question_ids, _node_id(edge, "from"))
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)

    for edge in edges:
        edge_type = _text(edge.get("edge_type"))
        event_id = _text(edge.get("evidence_event_id"))
        from_id = _node_id(edge, "from")
        to_id = _node_id(edge, "to")
        if edge_type == "question_has_rubric_item" and from_id in question_ids:
            _append_unique(rubric_item_ids, to_id)
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)
        if edge_type == "rubric_item_maps_to_error" and (from_id in rubric_item_ids or to_id == error_id):
            _append_unique(error_ids, to_id)
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)
        if edge_type == "submission_triggered_error" and to_id == error_id:
            _append_unique(error_ids, to_id)
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)
    if error_id:
        _append_unique(error_ids, error_id)

    for edge in edges:
        edge_type = _text(edge.get("edge_type"))
        event_id = _text(edge.get("evidence_event_id"))
        from_id = _node_id(edge, "from")
        to_id = _node_id(edge, "to")
        if edge_type == "error_points_to_training" and from_id in error_ids:
            _append_unique(training_target_ids, to_id)
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)
        if edge_type == "training_uses_question" and from_id in training_target_ids:
            _append_unique(question_ids, to_id)
            _append_unique(evidence_event_ids, event_id)
            related_edges.append(edge)

    for event_id in support_ids:
        _append_unique(evidence_event_ids, event_id)

    return {
        "concept_id": concept,
        "error_id": error_id,
        "question_ids": question_ids[:8],
        "rubric_item_ids": rubric_item_ids[:8],
        "error_ids": error_ids[:8],
        "training_target_ids": training_target_ids[:8],
        "evidence_event_ids": evidence_event_ids[:12],
        "related_edge_count": len(related_edges),
    }


def _weak_point_documents(
    projection: dict[str, Any],
    *,
    min_rank: int,
    max_chars_per_doc: int,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for raw_item in _as_list(projection.get("weak_points")):
        item = _as_dict(raw_item)
        if _is_stale_or_superseded(item):
            continue
        level = _text(item.get("evidence_level"))
        if _evidence_level_rank(level) < min_rank:
            continue
        concept_id = _text(item.get("concept_id"))
        error_code = _text(item.get("error_code"))
        if not concept_id or not error_code:
            continue
        raw_truth = item.get("current_truth") or item.get("claim") or f"{concept_id} 的 {error_code} 错因需要持续训练。"
        current_truth, redaction_count, heavily_sanitized = _sanitize_compiled_truth_text(
            raw_truth,
            max_chars=max(80, int(max_chars_per_doc)),
        )
        if not current_truth:
            continue
        supporting_event_ids = list(item.get("supporting_event_ids") or [])
        graph_context = _graph_context_for_weak_point(
            projection,
            concept_id=concept_id,
            error_code=error_code,
            supporting_event_ids=supporting_event_ids,
        )
        key = f"{concept_id}:{error_code}"
        docs.append({
            "chunk_id": f"compiled-truth:weak-point:{key}",
            "id": f"compiled-truth:weak-point:{key}",
            "card_title": "学员弱点: " + key,
            "title": "学员弱点: " + key,
            "source_type": "compiled_learning_truth",
            "_source_group": "compiled_learning_truth",
            "source": "learner_summaries.summary_structured_json.learning_brain",
            "rag_content": _format_weak_point_doc(
                concept_id=concept_id,
                error_code=error_code,
                truth=current_truth,
                item=item,
                graph_context=graph_context,
            ),
            "score": 0.0,
            "evidence_level": level,
            "supporting_event_ids": supporting_event_ids,
            "metadata": {
                "object_id": key,
                "object_type": "weak_point",
                "evidence_level": level,
                "projection_subject": _text(projection.get("subject")),
                "recommended_training": dict(item.get("recommended_training") or {}),
                "graph_context": graph_context,
                "security": {
                    "sanitized": True,
                    "redaction_count": redaction_count,
                },
            },
            "_compiled_truth_shadow_only": heavily_sanitized,
        })
    return docs


def materialize_compiled_truth_documents(
    compiled_projection: dict[str, Any] | None,
    *,
    max_documents: int = 6,
    min_evidence_level: str = "L1_repeated",
    max_chars_per_doc: int = _DEFAULT_MAX_CHARS_PER_DOC,
    max_total_chars: int = _DEFAULT_MAX_TOTAL_CHARS,
) -> list[dict[str, Any]]:
    projection = _projection_with_personalization_claims(_as_dict(compiled_projection))
    compiled_objects = _as_dict(projection.get("compiled_objects") or projection.get("objects"))
    weak_points = _as_list(projection.get("weak_points"))
    if not compiled_objects and not weak_points:
        return []

    min_rank = _evidence_level_rank(min_evidence_level)
    docs: list[dict[str, Any]] = _weak_point_documents(
        projection,
        min_rank=min_rank,
        max_chars_per_doc=max_chars_per_doc,
    )
    seen_ids = {_text(doc.get("chunk_id")) for doc in docs}
    for object_id, raw_item in compiled_objects.items():
        item = _as_dict(raw_item)
        if _is_stale_or_superseded(item):
            continue
        level = _text(item.get("evidence_level"))
        if _evidence_level_rank(level) < min_rank:
            continue
        current_truth, redaction_count, heavily_sanitized = _sanitize_compiled_truth_text(
            item.get("current_truth") or item.get("claim") or item.get("summary"),
            max_chars=max(80, int(max_chars_per_doc)),
        )
        if not current_truth:
            continue
        key = _text(object_id)
        chunk_id = f"compiled-truth:{key}"
        if chunk_id in seen_ids:
            continue
        doc = {
            "chunk_id": chunk_id,
            "id": chunk_id,
            "card_title": "学习事实: " + key,
            "title": "学习事实: " + key,
            "source_type": "compiled_learning_truth",
            "_source_group": "compiled_learning_truth",
            "source": "learner_summaries.summary_structured_json.learning_brain",
            "rag_content": _format_compiled_truth_doc(key, item, current_truth),
            "score": 0.0,
            "evidence_level": level,
            "supporting_event_ids": list(item.get("supporting_event_ids") or []),
            "metadata": {
                "object_id": key,
                "object_type": key.split(":", 1)[0] if ":" in key else "learning_object",
                "evidence_level": level,
                "projection_subject": _text(projection.get("subject")),
                "security": {
                    "sanitized": True,
                    "redaction_count": redaction_count,
                },
            },
            "_compiled_truth_shadow_only": heavily_sanitized,
        }
        docs.append(doc)

    docs.sort(
        key=lambda item: (
            _evidence_level_rank(_text(item.get("evidence_level"))),
            len(_as_list(item.get("supporting_event_ids"))),
            _text(item.get("chunk_id")),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    total_chars = 0
    for doc in docs[: max(0, int(max_documents))]:
        content = _text(doc.get("rag_content"))
        next_total = total_chars + len(content)
        if selected and next_total > max_total_chars:
            break
        if next_total > max_total_chars:
            doc = dict(doc)
            doc["rag_content"] = content[: max(0, int(max_total_chars))].rstrip()
        selected.append(doc)
        total_chars += len(_text(doc.get("rag_content")))
    return selected
