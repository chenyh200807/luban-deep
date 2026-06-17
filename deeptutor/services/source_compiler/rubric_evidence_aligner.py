from __future__ import annotations

import re
from typing import Any


def iter_evidence_records(payload: object, *, source_path: str, source_class: str) -> list[dict[str, Any]]:
    records = _payload_records(payload)
    evidence: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        text = _record_text(record)
        if not text:
            continue
        evidence.append(
            {
                "evidence_id": f"{source_path}:row_{index}",
                "source_path": source_path,
                "source_class": source_class,
                "source_record_id": record.get("chunk_id") or record.get("id") or record.get("source_record_id") or f"row_{index}",
                "node_code": _record_node_code(record),
                "title": _record_title(record),
                "content": text,
                "content_preview": _preview(text, 220),
            }
        )
    return evidence


def align_candidate_to_evidence(
    candidate: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    *,
    max_refs_per_point: int = 3,
) -> dict[str, Any]:
    aligned = dict(candidate)
    point_rows: list[dict[str, Any]] = []
    for point in list(candidate.get("scoring_points") or []):
        point_copy = dict(point)
        refs = _rank_evidence_refs(
            point_copy,
            evidence_records,
            node_code=str(candidate.get("node_code") or ""),
            max_refs=max_refs_per_point,
        )
        point_copy["evidence_refs"] = list(point_copy.get("evidence_refs") or []) + refs
        point_copy["evidence_alignment"] = {
            "aligned": bool(refs),
            "best_score": refs[0]["alignment_score"] if refs else 0.0,
            "method": "term_overlap_node_boost_mvp",
        }
        point_rows.append(point_copy)

    aligned["scoring_points"] = point_rows
    aligned["evidence_alignment_summary"] = _alignment_summary(point_rows)
    aligned["publishability"] = _publishability(aligned)
    aligned["review_status"] = "ready_for_review"
    aligned["derivation_scope"] = "answer_text_plus_evidence_alignment_mvp"
    return aligned


def build_review_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        publishability = candidate.get("publishability") or {}
        for point in candidate.get("scoring_points") or []:
            alignment = point.get("evidence_alignment") or {}
            rows.append(
                {
                    "stable_rubric_candidate_id": candidate.get("stable_rubric_candidate_id"),
                    "point_id": point.get("point_id"),
                    "ordinal": point.get("ordinal"),
                    "node_code": candidate.get("node_code"),
                    "exam_year": candidate.get("exam_year"),
                    "max_score": point.get("max_score"),
                    "confidence": point.get("confidence"),
                    "label": point.get("label"),
                    "expected_answer": point.get("expected_answer"),
                    "evidence_aligned": alignment.get("aligned", False),
                    "best_evidence_score": alignment.get("best_score", 0.0),
                    "publish_gate": publishability.get("gate"),
                    "review_decision": "pending",
                    "review_notes": "",
                }
            )
    return rows


def build_quality_report(candidates: list[dict[str, Any]], *, evidence_count: int) -> dict[str, Any]:
    point_count = sum(len(candidate.get("scoring_points") or []) for candidate in candidates)
    aligned_points = sum(
        1
        for candidate in candidates
        for point in candidate.get("scoring_points") or []
        if (point.get("evidence_alignment") or {}).get("aligned")
    )
    publishable = sum(1 for candidate in candidates if (candidate.get("publishability") or {}).get("gate") == "publishable_candidate")
    review_required = sum(1 for candidate in candidates if (candidate.get("publishability") or {}).get("gate") == "review_required")
    blocked = sum(1 for candidate in candidates if (candidate.get("publishability") or {}).get("gate") == "blocked")
    return {
        "candidates": len(candidates),
        "points": point_count,
        "evidence_records": evidence_count,
        "aligned_points": aligned_points,
        "point_alignment_rate": round(aligned_points / point_count, 4) if point_count else 0,
        "publishable_candidates": publishable,
        "review_required_candidates": review_required,
        "blocked_candidates": blocked,
        "publishable_rate": round(publishable / len(candidates), 4) if candidates else 0,
    }


def _payload_records(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("content_blocks", "nodes", "chunks", "records", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def _record_text(record: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("content_markdown", "rag_content", "content", "text", "summary", "title"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            pieces.append(value)
    source_context = record.get("source_context")
    if isinstance(source_context, dict):
        origin = source_context.get("origin_text")
        if isinstance(origin, str) and origin.strip():
            pieces.append(origin)
    for key in ("knowledge_cards", "structured_rules", "key_parameters", "synthetic_qa", "common_violations"):
        value = record.get(key)
        if value:
            pieces.append(str(value))
    return "\n".join(pieces).strip()


def _record_node_code(record: dict[str, Any]) -> str | None:
    taxonomy = record.get("taxonomy")
    if isinstance(taxonomy, dict) and taxonomy.get("node_code"):
        return str(taxonomy.get("node_code"))
    if record.get("node_code"):
        return str(record.get("node_code"))
    source_context = record.get("source_context")
    if isinstance(source_context, dict) and source_context.get("taxonomy_node_code"):
        return str(source_context.get("taxonomy_node_code"))
    return None


def _record_title(record: dict[str, Any]) -> str:
    taxonomy = record.get("taxonomy")
    if isinstance(taxonomy, dict):
        for key in ("topic", "node_name", "taxonomy_path"):
            if taxonomy.get(key):
                return str(taxonomy.get(key))
    source_context = record.get("source_context")
    if isinstance(source_context, dict):
        title = " ".join(
            str(source_context.get(key) or "")
            for key in ("standard_code", "article_id", "chapter_name")
            if source_context.get(key)
        ).strip()
        if title:
            return title
    return str(record.get("title") or record.get("chunk_id") or record.get("id") or "")


def _rank_evidence_refs(
    point: dict[str, Any],
    evidence_records: list[dict[str, Any]],
    *,
    node_code: str,
    max_refs: int,
) -> list[dict[str, Any]]:
    query_terms = _terms(" ".join([str(point.get("label") or ""), str(point.get("expected_answer") or "")]))
    if not query_terms:
        return []
    ranked: list[tuple[float, dict[str, Any]]] = []
    for record in evidence_records:
        content = str(record.get("content") or "")
        content_terms = _terms(content)
        overlap = query_terms & content_terms
        if not overlap:
            continue
        score = len(overlap) / max(1, len(query_terms))
        if node_code and str(record.get("node_code") or "").startswith(node_code[:5]):
            score += 0.15
        if str(record.get("source_class")) == "standard":
            score += 0.05
        ranked.append((score, record))
    ranked.sort(key=lambda item: item[0], reverse=True)
    refs: list[dict[str, Any]] = []
    for score, record in ranked[:max_refs]:
        refs.append(
            {
                "source_type": record.get("source_class"),
                "source_path": record.get("source_path"),
                "source_record_id": record.get("source_record_id"),
                "node_code": record.get("node_code"),
                "title": record.get("title"),
                "content_preview": record.get("content_preview"),
                "alignment_score": round(score, 4),
                "method": "term_overlap_node_boost_mvp",
            }
        )
    return refs


def _terms(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", str(text or ""))
    terms = set(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,8}", normalized))
    domain_terms = {
        term
        for term in (
            "复打法",
            "反插法",
            "钢筋笼",
            "拔管",
            "成桩",
            "温升值",
            "里表温差",
            "降温速率",
            "测温点",
            "表层",
            "底层",
            "中心温度",
            "麻面",
            "蜂窝",
            "孔洞",
            "露筋",
            "自检",
            "互检",
            "工序交接检查",
            "三检制",
            "限制",
            "禁止",
            "施工升降机",
            "LED灯",
        )
        if term in normalized
    }
    return terms | domain_terms


def _alignment_summary(points: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(points)
    aligned = sum(1 for point in points if (point.get("evidence_alignment") or {}).get("aligned"))
    return {
        "points": total,
        "aligned_points": aligned,
        "alignment_rate": round(aligned / total, 4) if total else 0,
    }


def _publishability(candidate: dict[str, Any]) -> dict[str, Any]:
    warnings = set(candidate.get("warnings") or [])
    summary = candidate.get("evidence_alignment_summary") or {}
    confidence = str(candidate.get("overall_confidence") or "")
    reasons: list[str] = []
    if confidence.startswith("C"):
        reasons.append("low_confidence")
    if "total_score_missing" in warnings or "point_score_missing" in warnings:
        reasons.append("missing_score")
    if float(summary.get("alignment_rate") or 0) < 0.5:
        reasons.append("low_evidence_alignment")
    if not reasons:
        gate = "publishable_candidate"
    elif reasons == ["low_evidence_alignment"]:
        gate = "review_required"
    else:
        gate = "blocked"
    return {
        "gate": gate,
        "reasons": reasons,
        "requires_human_review": True,
    }


def _preview(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
