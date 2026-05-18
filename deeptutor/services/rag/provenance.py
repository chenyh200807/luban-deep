"""Provenance features and source-aware ranking helpers for RAG."""

from __future__ import annotations

from typing import Any


_AUTHORITY_RANK = {
    "exact_question": 100,
    "question_exact_text": 100,
    "question_exact_vector": 95,
    "standard_code_exact": 90,
    "standard_precision": 88,
    "standard": 80,
    "questions_bank": 70,
    "compiled_learning_truth": 55,
    "textbook": 45,
    "exam": 40,
}

_EVIDENCE_RANK = {
    "L0_observed": 0,
    "L1_repeated": 1,
    "L2_confirmed": 2,
    "L3_mastery_signal": 3,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_group(doc: dict[str, Any]) -> str:
    return _text(doc.get("_source_group") or doc.get("source_group") or doc.get("source_type"))


def extract_provenance_features(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    group = _source_group(doc)
    evidence_level = _text(doc.get("evidence_level") or metadata.get("evidence_level"))
    authority_rank = _AUTHORITY_RANK.get(group, _AUTHORITY_RANK.get(_text(doc.get("source_type")), 10))
    return {
        "chunk_id": _text(doc.get("chunk_id") or doc.get("id")),
        "source_group": group,
        "source_type": _text(doc.get("source_type")),
        "authority_rank": authority_rank,
        "evidence_level": evidence_level,
        "evidence_level_rank": _EVIDENCE_RANK.get(evidence_level, -1),
        "manual_confirmed": evidence_level == "L2_confirmed",
        "stale": bool(doc.get("stale") or metadata.get("stale")),
        "supporting_event_ids": list(doc.get("supporting_event_ids") or metadata.get("supporting_event_ids") or []),
        "supporting_event_count": len(doc.get("supporting_event_ids") or []),
    }


def annotate_provenance_features(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        item["_provenance_features"] = extract_provenance_features(item)
        item["_provenance_rank_adjustment"] = 0.0
        annotated.append(item)
    return annotated


def apply_provenance_ranking(
    docs: list[dict[str, Any]],
    *,
    exact_question_present: bool = False,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    if not enabled:
        return annotate_provenance_features(docs)

    ranked: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        features = extract_provenance_features(item)
        item["_provenance_features"] = features
        base_score = float(item.get("weighted_rrf_score") or item.get("score") or 0.0)
        boost = 0.0
        group = features["source_group"]
        if group == "compiled_learning_truth":
            boost += min(0.012, max(0, features["evidence_level_rank"]) * 0.004)
            boost += min(0.006, features["supporting_event_count"] * 0.001)
            if exact_question_present:
                boost -= 0.02
        elif group in {"standard_code_exact", "standard_precision"}:
            boost += 0.02
        elif group in {"question_exact_text", "question_exact_vector"}:
            boost += 0.04
        item["weighted_rrf_score"] = base_score + boost
        item["_provenance_rank_adjustment"] = round(boost, 6)
        ranked.append(item)
    ranked.sort(
        key=lambda item: (
            float(item.get("weighted_rrf_score") or 0.0),
            int((item.get("_provenance_features") or {}).get("authority_rank") or 0),
        ),
        reverse=True,
    )
    if exact_question_present:
        exact_head = [
            item
            for item in ranked
            if (item.get("_provenance_features") or {}).get("source_group")
            in {"question_exact_text", "question_exact_vector"}
        ]
        others = [item for item in ranked if item not in exact_head]
        return exact_head + others
    return ranked


def build_ranking_trace(
    docs: list[dict[str, Any]],
    *,
    authority_order: list[str] | None = None,
    shadow_sources: list[dict[str, Any]] | None = None,
    ranking_policy: dict[str, Any] | None = None,
    max_features: int = 20,
) -> dict[str, Any]:
    features = [extract_provenance_features(doc) for doc in docs]
    shadow = [extract_provenance_features(doc) for doc in list(shadow_sources or [])]
    return {
        "fusion": "weighted_rrf_with_provenance",
        "authority_order": list(authority_order or _AUTHORITY_RANK.keys()),
        "ranking_policy": dict(ranking_policy or {}),
        "provenance_features": features[:max(0, int(max_features))],
        "shadow_sources": shadow[:max(0, int(max_features))],
        "shadow_source_count": len(shadow),
    }
