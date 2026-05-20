from __future__ import annotations

import re
from typing import Any, Literal

from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label

LEARNING_BRAIN_SUBJECT = "construction_exam_learning_truth"
_ERROR_LABELS = {
    "E01": "知识点缺失",
    "E02": "采分点遗漏",
    "E03": "关键词缺失",
    "E04": "口号化表达",
    "E05": "审题错误",
    "E06": "程序顺序错误",
    "E07": "概念混淆",
    "E08": "背景信息提取失败",
    "E09": "计算错误",
    "E10": "规范适用错误",
    "E11": "迁移失败",
    "E12": "表达冗余",
    "M01": "知识点不熟",
    "M02": "关键词误读",
    "M03": "概念混淆",
    "M04": "选项陷阱",
    "M05": "审题方向错误",
    "M06": "多选漏选",
    "M07": "多选错选",
    "M08": "规范数字混淆",
    "M09": "题干条件提取不完整",
    "M10": "用常识替代规范判断",
}
_ERROR_HINTS = {
    "M06": "多选题遗漏了应选项，需要回到题干条件逐项核对。",
    "M07": "多选题选入了干扰项，需要辨别选项是否偷换主体、条件或数字。",
}
_EVIDENCE_LEVEL_LABELS = {
    "L0_observed": "单次观察",
    "L1_repeated": "重复出现",
    "L2_confirmed": "已确认",
    "L3_mastery_signal": "改善信号",
    "unclassified": "待确认",
}
_EDGE_LABELS = {
    "question_tests_concept": "题目考查知识点",
    "question_has_rubric_item": "题目包含采分点",
    "rubric_item_maps_to_error": "采分点对应错因",
    "submission_answered_question": "作答对应题目",
    "submission_missed_rubric_item": "作答漏掉采分点",
    "submission_triggered_error": "作答触发错因",
    "error_points_to_training": "错因指向训练",
    "weak_point_drives_training": "薄弱点驱动训练",
    "training_uses_question": "训练使用题目",
    "training_improved_error": "训练后已改善",
    "training_not_improved_error": "训练后仍需巩固",
}
_TRAINING_FOCUS_LABELS = {
    "case_repair": "案例题补强",
    "projected_rubric": "采分点补强",
    "open_skill": "开放作答训练",
}


def wrap_learning_brain_projection(projection: dict[str, Any]) -> dict[str, Any]:
    return {"learning_brain": dict(projection or {})}


def extract_learning_brain_projection(payload: dict[str, Any] | None) -> dict[str, Any]:
    structured = _dict(payload)
    nested = _dict(structured.get("learning_brain"))
    if _is_learning_brain_projection(nested):
        return nested
    # Compatibility reader for rows written before the namespaced storage contract.
    if _is_learning_brain_projection(structured):
        return structured
    return {}


def build_learning_brain_read_model(
    *,
    user_id: str,
    projection: dict[str, Any],
    surface: Literal["mobile", "qa"] = "mobile",
) -> dict[str, Any]:
    normalized_projection = dict(projection or {})
    typed_graph = _dict(normalized_projection.get("typed_graph"))
    typed_graph_edges = [
        _with_edge_display(dict(edge)) for edge in list(typed_graph.get("edges") or []) if isinstance(edge, dict)
    ]
    compiled_objects = {
        str(key): _with_object_display({
            **dict(value),
            "object_key": str(key),
            "current_truth": _humanize_text(value.get("current_truth", "")),
        })
        for key, value in dict(normalized_projection.get("compiled_objects") or {}).items()
        if isinstance(value, dict)
    }
    weak_points = [
        _with_training_display({**dict(item), "claim": _humanize_text(item.get("claim", ""))})
        for item in list(normalized_projection.get("weak_points") or [])
        if isinstance(item, dict)
    ]
    improvement_signals = [
        dict(item) for item in list(normalized_projection.get("improvement_signals") or []) if isinstance(item, dict)
    ]
    stale_claims = [dict(item) for item in list(normalized_projection.get("stale_claims") or []) if isinstance(item, dict)]
    run = _dict(normalized_projection.get("synthesis_run"))
    graph_chain = build_learning_brain_graph_chain(
        typed_graph_edges=typed_graph_edges,
        weak_points=weak_points,
        improvement_signals=improvement_signals,
    )
    derived_graph_edges = (
        graph_chain["training_uses_question"]
        + graph_chain["training_improved_error"]
        + graph_chain["training_not_improved_error"]
    )
    visible_typed_graph_edges = typed_graph_edges + derived_graph_edges
    base = {
        "ok": True,
        "user_id": user_id,
        "projection_subject": str(normalized_projection.get("subject") or LEARNING_BRAIN_SUBJECT),
        "schema_version": int(normalized_projection.get("schema_version") or 0),
        "compiled_objects": compiled_objects,
        "weak_points": weak_points,
        "improvement_signals": improvement_signals,
        "stale_claims": stale_claims,
        "typed_graph_edges": visible_typed_graph_edges,
        "typed_graph_readiness_gaps": list(typed_graph.get("readiness_gaps") or []),
        "typed_graph_edge_count": len(visible_typed_graph_edges),
        "graph_chain": graph_chain,
        "event_count": int(run.get("input_event_count") or 0),
        "created_claim_count": int(run.get("created_claim_count") or 0),
        "decayed_claim_count": int(run.get("decayed_claim_count") or 0),
        "output_projection_hash": str(run.get("output_projection_hash") or ""),
        "synthesis_run": run,
    }
    if surface == "qa":
        base["visible_sections"] = _qa_sections(
            weak_points=weak_points,
            compiled_objects=compiled_objects,
            typed_graph=typed_graph,
            typed_graph_edges=visible_typed_graph_edges,
        )
    else:
        base["visible_sections"] = _mobile_sections(
            compiled_objects=compiled_objects,
            typed_graph=typed_graph,
            weak_points=weak_points,
            improvement_signals=improvement_signals,
            graph_chain=graph_chain,
        )
    return base


def build_learning_brain_graph_chain(
    *,
    typed_graph_edges: list[dict[str, Any]],
    weak_points: list[dict[str, Any]],
    improvement_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    question_edges_by_concept: dict[str, list[dict[str, Any]]] = {}
    for edge in typed_graph_edges:
        if edge.get("edge_type") != "question_tests_concept":
            continue
        concept_id = _node_id(edge, "to")
        if concept_id:
            question_edges_by_concept.setdefault(concept_id, []).append(edge)

    active_error_ids = {
        f"{str(item.get('concept_id') or '').strip()}:{str(item.get('error_code') or '').strip()}"
        for item in weak_points
        if str(item.get("concept_id") or "").strip() and str(item.get("error_code") or "").strip()
    }
    improved_error_ids = {
        f"{str(item.get('concept_id') or '').strip()}:{str(item.get('error_code') or '').strip()}"
        for item in improvement_signals
        if str(item.get("concept_id") or "").strip() and str(item.get("error_code") or "").strip()
    }
    improved_concepts = {
        str(item.get("concept_id") or "").strip()
        for item in improvement_signals
        if str(item.get("concept_id") or "").strip() and not str(item.get("error_code") or "").strip()
    }
    training_uses_question: list[dict[str, Any]] = []
    training_improved_error: list[dict[str, Any]] = []
    training_not_improved_error: list[dict[str, Any]] = []
    error_to_training = [edge for edge in typed_graph_edges if edge.get("edge_type") == "error_points_to_training"]
    for edge in error_to_training:
        error_id = _node_id(edge, "from")
        training_id = _node_id(edge, "to")
        concept_id = _concept_from_error_id(error_id)
        selected_question = next(iter(question_edges_by_concept.get(concept_id, [])), None)
        if not error_id or not training_id or not selected_question:
            continue
        question_id = _node_id(selected_question, "from")
        training_uses_question.append(_with_edge_display({
            "edge_type": "training_uses_question",
            "from": {"type": "next_training", "id": training_id},
            "to": {"type": "question", "id": question_id},
            "source_feature": "learning_brain_read_model",
            "reason_edge_event_id": edge.get("evidence_event_id", ""),
            "selected_question_event_id": selected_question.get("evidence_event_id", ""),
            "confidence": edge.get("confidence", 0.8),
        }))
        outcome = {
            "from": {"type": "next_training", "id": training_id},
            "to": {"type": "error", "id": error_id},
            "source_feature": "learning_brain_read_model",
            "question_id": question_id,
            "reason_edge_event_id": edge.get("evidence_event_id", ""),
            "confidence": edge.get("confidence", 0.8),
        }
        if error_id in active_error_ids:
            training_not_improved_error.append(_with_edge_display({
                "edge_type": "training_not_improved_error",
                "reason": "weak_point_still_active",
                **outcome,
            }))
        elif error_id in improved_error_ids or concept_id in improved_concepts:
            training_improved_error.append(_with_edge_display({"edge_type": "training_improved_error", **outcome}))
    return {
        "error_points_to_training": [_with_edge_display(edge) for edge in error_to_training],
        "training_uses_question": training_uses_question,
        "training_improved_error": training_improved_error,
        "training_not_improved_error": training_not_improved_error,
        "has_training_uses_question": bool(training_uses_question),
        "has_training_improved_error": bool(training_improved_error),
        "has_training_not_improved_error": bool(training_not_improved_error),
    }


def _mobile_sections(
    *,
    compiled_objects: dict[str, dict[str, Any]],
    typed_graph: dict[str, Any],
    weak_points: list[dict[str, Any]],
    improvement_signals: list[dict[str, Any]],
    graph_chain: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    truth_objects = [
        _without_internal_refs(_with_object_display({
            "object_key": key,
            "object_type": value.get("object_type", ""),
            "object_id": value.get("object_id", ""),
            "current_truth": _humanize_text(value.get("current_truth", "")),
            "evidence_level": value.get("evidence_level", ""),
            "evidence_level_label": _evidence_level_label(value.get("evidence_level", "")),
            "confidence": value.get("confidence", 0),
            "decay_state": value.get("decay_state", ""),
            "supporting_event_ids": list(value.get("supporting_event_ids") or []),
            "supporting_event_labels": _event_labels(value.get("supporting_event_ids")),
            "conflicting_event_ids": list(value.get("conflicting_event_ids") or []),
            "timeline_refs": list(value.get("timeline_refs") or []),
        }))
        for key, value in compiled_objects.items()
        if str(key).startswith(("concept:", "error:", "question:", "rubric_item:", "submission:", "training:", "next_training:"))
    ][:6]
    evidence_items = [
        {
            "event_id": "",
            "object_key": item["object_key"],
            "object_type": item["object_type"],
            "evidence_level": item["evidence_level"],
            "evidence_level_label": item.get("evidence_level_label", ""),
            "edge_type": "",
            "path": item.get("display_title") or item["object_key"],
            "display_label": item.get("display_label", ""),
            "display_title": item.get("display_title", ""),
            "display_meta": item.get("display_meta", ""),
            "display_path": item.get("display_title") or item["object_key"],
            "event_label": _event_label(index),
        }
        for item in truth_objects
        for index, _event_id in enumerate(item["supporting_event_ids"][:3])
    ][:12]
    for edge in (
        graph_chain["training_uses_question"][:4]
        + graph_chain["training_improved_error"][:4]
        + graph_chain["training_not_improved_error"][:4]
    ):
        from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
        to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
        evidence_items.append({
            "event_id": "",
            "object_key": "",
            "object_type": "typed_graph",
            "evidence_level": str(edge.get("edge_type") or ""),
            "edge_type": str(edge.get("edge_type") or ""),
            "path": edge.get("display_path")
            or " -> ".join(item for item in [str(from_node.get("id") or ""), str(to_node.get("id") or "")] if item),
            "display_label": edge.get("display_label", ""),
            "display_title": edge.get("display_title", ""),
            "display_meta": edge.get("display_meta", ""),
            "display_path": edge.get("display_path", ""),
            "event_label": "训练链证据",
        })
    training_items = [
        _with_training_display({
            "concept_id": weak.get("concept_id", ""),
            "error_code": weak.get("error_code", ""),
            "claim": _humanize_text(weak.get("claim", "")),
            "evidence_level": weak.get("evidence_level", ""),
            "evidence_level_label": _evidence_level_label(weak.get("evidence_level", "")),
            "recommended_training": dict(weak.get("recommended_training") or {}),
            "supporting_event_ids": list(weak.get("supporting_event_ids") or []),
            "supporting_event_labels": _event_labels(weak.get("supporting_event_ids")),
        })
        for weak in weak_points
    ][:5]
    if not training_items and improvement_signals:
        training_items = [
            _with_training_display({
                "concept_id": item.get("concept_id", ""),
                "error_code": item.get("error_code", ""),
                "claim": "后续训练已出现改善信号",
                "evidence_level": "improving",
                "evidence_level_label": "改善中",
                "recommended_training": {},
                "supporting_event_ids": [item.get("event_id", "")],
            })
            for item in improvement_signals[:5]
        ]
    return {
        "current_truth": [_without_visible_evidence_refs(item) for item in truth_objects],
        "evidence_flow": evidence_items,
        "next_training": [_without_visible_evidence_refs(item) for item in training_items],
    }


def _qa_sections(
    *,
    weak_points: list[dict[str, Any]],
    compiled_objects: dict[str, dict[str, Any]],
    typed_graph: dict[str, Any],
    typed_graph_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "weak_points",
            "visible": bool(weak_points),
            "item_count": len(weak_points),
            "items": weak_points[:8],
        },
        {
            "id": "compiled_objects",
            "visible": bool(compiled_objects),
            "item_count": len(compiled_objects),
            "object_keys": sorted(compiled_objects)[:24],
        },
        {
            "id": "typed_graph",
            "visible": bool(typed_graph_edges),
            "item_count": len(typed_graph_edges),
            "readiness_gaps": list(typed_graph.get("readiness_gaps") or []),
        },
    ]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _is_learning_brain_projection(value: dict[str, Any]) -> bool:
    if str(value.get("subject") or "").strip() != LEARNING_BRAIN_SUBJECT:
        return False
    if not isinstance(value.get("compiled_objects", {}), dict):
        return False
    if not isinstance(value.get("weak_points", []), list):
        return False
    if not isinstance(value.get("typed_graph", {}), dict):
        return False
    return True


def _node_id(edge: dict[str, Any], side: str) -> str:
    node = edge.get(side) if isinstance(edge.get(side), dict) else {}
    return str(node.get("id") or "").strip()


def _concept_from_error_id(error_id: str) -> str:
    return error_id.split(":", 1)[0].strip() if ":" in error_id else ""


def _evidence_level_label(level: Any) -> str:
    key = str(level or "").strip()
    return _EVIDENCE_LEVEL_LABELS.get(key) or key or _EVIDENCE_LEVEL_LABELS["unclassified"]


def _concept_label(concept_id: Any) -> str:
    code = str(concept_id or "").strip().upper()
    if not code:
        return ""
    if re.match(r"^1A\d{6}$", code):
        return display_taxonomy_label(code, fallback=code)
    text = str(concept_id or "").strip()
    match = re.search(r"我想练习(.+?)相关的题目", text)
    if match:
        return match.group(1).strip()
    text = re.sub(r"\s*请严格围绕.*$", "", text).strip()
    text = re.sub(r"\s*当前学习锚点.*$", "", text).strip()
    return text[:24] if len(text) > 24 else text


def _error_label(error_code: Any) -> str:
    code = str(error_code or "").strip().upper()
    if not code:
        return ""
    return _ERROR_LABELS.get(code) or f"错因 {code}"


def _event_label(index: int) -> str:
    if index == 0:
        return "最近一次批改"
    if index == 1:
        return "上一次批改"
    return f"第 {index + 1} 条批改证据"


def _event_labels(ids: Any) -> list[str]:
    return [_event_label(index) for index, _item in enumerate(list(ids or [])[:3])]


def _compact_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"{text[:8]}...{text[-4:]}" if len(text) > 18 else text


def _question_label(question_id: Any) -> str:
    text = str(question_id or "").strip()
    if not text:
        return ""
    match = re.match(r"^wechat-harness-case-(\d+)$", text, flags=re.IGNORECASE)
    if match:
        return f"专项训练 {match.group(1)}"
    match = re.match(r"^case[-_:]?(\d+)$", text, flags=re.IGNORECASE)
    if match:
        return f"第 {match.group(1)} 题"
    match = re.match(r"^q[-_:]?(\d+)$", text, flags=re.IGNORECASE)
    if match:
        return f"第 {match.group(1)} 题"
    return _compact_id(text)


def _submission_label(submission_id: Any) -> str:
    text = str(submission_id or "").strip()
    if not text:
        return ""
    match = re.match(r"^wechat-harness-learning-brain-[a-z0-9]+-(\d+)$", text, flags=re.IGNORECASE)
    if match:
        return f"第 {match.group(1)} 次作答"
    if re.match(r"^wechat-harness-learning-brain-confirm-[a-z0-9]+$", text, flags=re.IGNORECASE):
        return "老师确认"
    return _compact_id(text)


def _split_object_id(raw_id: Any, raw_type: Any = "") -> tuple[str, str]:
    object_id = str(raw_id or "").strip()
    object_type = str(raw_type or "").strip()
    if object_id.startswith("rubric_item:"):
        return "rubric_item", object_id.removeprefix("rubric_item:")
    if ":" in object_id:
        prefix, rest = object_id.split(":", 1)
        if prefix in {"concept", "error", "question", "submission", "training", "next_training", "rubric"}:
            return ("rubric_item" if prefix == "rubric" else prefix), rest
    return object_type, object_id


def _object_display(raw_id: Any, raw_type: Any = "") -> dict[str, str]:
    object_type, object_id = _split_object_id(raw_id, raw_type)
    if object_type in {"training", "next_training"}:
        parts = str(object_id or "").split(":")
        if str(object_id).startswith("practice /"):
            readable = _humanize_text(object_id).replace("训练建议：", "").strip()
            return {"display_label": "训练建议", "display_title": f"训练建议：{readable}", "display_meta": readable}
        concept = _concept_label(parts[0]) if parts else ""
        error = _error_label(parts[1]) if len(parts) > 1 and re.match(r"^[EM]\d{2}$", parts[1], flags=re.IGNORECASE) else ""
        focus = " / ".join(_TRAINING_FOCUS_LABELS.get(part, part) for part in parts[2:] if part)
        title_tail = focus or " / ".join(item for item in (concept, error) if item) or _compact_id(object_id)
        return {"display_label": "训练建议", "display_title": f"训练建议：{title_tail}", "display_meta": " / ".join(item for item in (concept, error) if item)}
    if (
        object_type == "error"
        or re.match(r"^[EM]\d{2}$", str(object_id), flags=re.IGNORECASE)
        or re.search(r":[EM]\d{2}$", str(object_id), flags=re.IGNORECASE)
    ):
        parts = str(object_id or "").split(":")
        concept = _concept_label(parts[0]) if len(parts) > 1 else ""
        error = _error_label(parts[-1])
        meta = " / ".join(item for item in (concept, error) if item)
        return {"display_label": "错因", "display_title": f"错因：{meta or error}", "display_meta": meta or error}
    if object_type == "question":
        label = _question_label(object_id)
        return {"display_label": "案例题", "display_title": f"案例题：{label}", "display_meta": f"案例题：{label}"}
    if object_type == "rubric_item":
        part = str(object_id or "").split(":")[-1]
        return {"display_label": "采分点", "display_title": f"采分点：{_compact_id(part)}", "display_meta": str(object_id or "")}
    if object_type == "concept" or str(object_id).upper().startswith("1A"):
        label = _concept_label(object_id)
        return {"display_label": "知识点", "display_title": f"知识点：{label}", "display_meta": str(object_id or "").upper()}
    if object_type == "submission":
        label = _submission_label(object_id)
        return {"display_label": "作答记录", "display_title": f"作答记录：{label}", "display_meta": f"作答记录：{label}"}
    return {"display_label": "学习对象", "display_title": f"学习对象：{_compact_id(object_id or object_type)}", "display_meta": str(object_id or "")}


def _edge_label(edge_type: Any) -> str:
    key = str(edge_type or "").strip()
    return _EDGE_LABELS.get(key) or "学习关系"


def _with_edge_display(edge: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(edge)
    from_node = edge.get("from") if isinstance(edge.get("from"), dict) else {}
    to_node = edge.get("to") if isinstance(edge.get("to"), dict) else {}
    from_display = _object_display(from_node.get("id") or from_node.get("type"), from_node.get("type", ""))
    to_display = _object_display(to_node.get("id") or to_node.get("type"), to_node.get("type", ""))
    label = _edge_label(edge.get("edge_type"))
    path = " → ".join(item for item in (from_display["display_title"], to_display["display_title"]) if item)
    enriched.update({
        "display_label": label,
        "display_title": label,
        "display_meta": path,
        "display_path": path,
    })
    return enriched


def _with_object_display(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    display = _object_display(enriched.get("object_id") or enriched.get("object_key"), enriched.get("object_type", ""))
    title = _humanize_text(enriched.get("current_truth")) or display["display_title"]
    enriched.update({
        "display_label": display["display_label"],
        "display_title": title,
        "display_meta": display["display_title"],
    })
    return enriched


def _without_internal_refs(item: dict[str, Any]) -> dict[str, Any]:
    visible = dict(item)
    visible["object_key"] = ""
    visible["object_id"] = ""
    visible["timeline_refs"] = []
    visible["conflicting_event_ids"] = []
    return visible


def _without_visible_evidence_refs(item: dict[str, Any]) -> dict[str, Any]:
    visible = dict(item)
    visible["supporting_event_ids"] = []
    visible["concept_id"] = ""
    visible["error_code"] = ""
    visible["recommended_training"] = {}
    return visible


def _with_training_display(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    concept = _concept_label(enriched.get("concept_id"))
    error = _error_label(enriched.get("error_code"))
    recommendation = _dict(enriched.get("recommended_training"))
    focus = _TRAINING_FOCUS_LABELS.get(str(recommendation.get("mode") or "").strip(), "") or str(
        recommendation.get("focus") or ""
    ).strip()
    title = str(enriched.get("claim") or "").strip()
    if not title:
        title = " / ".join(item for item in (concept, error) if item) or "下一步训练"
    enriched.update({
        "display_label": "训练建议",
        "display_title": _humanize_text(title),
        "display_meta": "；".join(
            item
            for item in (
                concept and f"知识点：{concept}",
                error and f"错因：{error}",
                _ERROR_HINTS.get(str(enriched.get("error_code") or "").strip().upper(), ""),
                focus,
            )
            if item
        ),
    })
    return enriched


def _humanize_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"我想练习(.+?)相关的题目\s*请严格围绕.*?当前学习锚点出题", r"\1", text)
    text = re.sub(r"\bpractice\s*/\s*", "训练建议：", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*->\s*", " → ", text)
    text = re.sub(r"\bq[-_:]?(\d+)\b", lambda match: f"第 {match.group(1)} 题", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bwechat-harness-case-(\d+)\b",
        lambda match: f"专项训练 {match.group(1)}",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bcase[-_:]?(\d+)\b",
        lambda match: f"第 {match.group(1)} 题",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bwechat-harness-learning-brain-[a-z0-9]+-(\d+)\b",
        lambda match: f"第 {match.group(1)} 次作答",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bwechat-harness-learning-brain-confirm-[a-z0-9]+\b",
        "老师确认",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b1A\d{6}\b", lambda match: display_taxonomy_label(match.group(0), fallback=match.group(0)), text)
    for error_code, label in _ERROR_LABELS.items():
        text = text.replace(error_code, label)
    return (
        text.replace("concept:", "知识点：")
        .replace("error:", "错因：")
        .replace("question_tests_concept", _EDGE_LABELS["question_tests_concept"])
        .replace("案例题： 第", "案例题：第")
        .replace("错因观察", "错因")
    )
