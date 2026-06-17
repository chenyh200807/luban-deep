from __future__ import annotations

import re
from typing import Any

from .metadata import with_compiler_metadata
from .schema import content_hash, stable_hash


_SCORE_RE = re.compile(r"[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]")
_SUBQUESTION_RE = re.compile(
    r"(?m)^\s*(\d+)[.、]\s*[（(]\s*本小题\s*(\d+(?:\.\d+)?)\s*分\s*[）)]"
)
_PAREN_ITEM_RE = re.compile(r"(?ms)^\s*[（(](\d+)[）)]\s*(.+?)(?=^\s*[（(]\d+[）)]|\Z)")
_ALPHA_ITEM_RE = re.compile(r"([A-Z])\s*[:：]\s*([^；;\n]+)")
_CIRCLED_CHARS = "①②③④⑤⑥⑦⑧⑨⑩"
_CIRCLED_SPLIT_RE = re.compile(f"([{_CIRCLED_CHARS}])")


def iter_case_study_answer_records(payload: object, *, source_path: str) -> list[dict[str, Any]]:
    """Return case-study answer records from cleaned 2026 question payloads."""

    records: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            for chunk_index, chunk in enumerate(chunks):
                if not isinstance(chunk, dict):
                    continue
                exercises = chunk.get("exercises")
                if not isinstance(exercises, list):
                    continue
                for exercise_index, exercise in enumerate(exercises):
                    if not isinstance(exercise, dict) or exercise.get("type") != "case_study":
                        continue
                    question_data = exercise.get("question_data") or {}
                    if not isinstance(question_data, dict):
                        continue
                    records.append(
                        {
                            "source_path": source_path,
                            "source_chunk_id": chunk.get("chunk_id"),
                            "source_index": f"{chunk_index}.{exercise_index}",
                            "question_type": "case_study",
                            "node_code": exercise.get("predicted_node")
                            or (chunk.get("taxonomy") or {}).get("node_code"),
                            "exam_year": (chunk.get("source_meta") or {}).get("exam_year"),
                            "stem": question_data.get("stem") or "",
                            "correct_answer": question_data.get("correct_answer") or "",
                            "analysis": question_data.get("analysis") or "",
                            "score": question_data.get("score"),
                            "source_meta": chunk.get("source_meta") or {},
                        }
                    )
    return records


def compile_answer_derived_rubric_candidate(
    record: dict[str, Any],
    *,
    run_id: str,
    source_path: str,
    compiled_at: str,
) -> dict[str, Any] | None:
    if record.get("question_type") != "case_study":
        return None
    answer = str(record.get("correct_answer") or "").strip()
    if not answer:
        return None

    source_seed = "|".join(
        [
            source_path,
            str(record.get("source_chunk_id") or ""),
            str(record.get("source_index") or ""),
            content_hash(answer),
        ]
    )
    segments = _segment_subquestions(answer, record.get("score"))
    points: list[dict[str, Any]] = []
    warnings: list[str] = []
    for segment in segments:
        extracted = _extract_points_from_segment(
            segment["text"],
            subquestion_index=segment["subquestion_index"],
            subquestion_score=segment["subquestion_score"],
        )
        if not extracted:
            warnings.append(f"subquestion_{segment['subquestion_index'] or 'all'}:no_points_extracted")
            continue
        points.extend(extracted)

    if not points:
        points.append(
            _point(
                label=_strip_answer_header(answer),
                expected_answer=_strip_answer_header(answer),
                max_score=_coerce_float(record.get("score")),
                match_type="whole_answer_fallback",
                confidence="C",
                derivation_method="fallback_whole_answer",
                subquestion_index=None,
            )
        )
        warnings.append("fallback_whole_answer_requires_review")

    for index, point in enumerate(points, start=1):
        point["point_id"] = stable_hash(f"{source_seed}|{index}|{point['label']}", prefix="sp_")
        point["ordinal"] = index
        point["evidence_refs"] = [
            {
                "source_type": "exam_answer",
                "source_path": source_path,
                "source_chunk_id": record.get("source_chunk_id"),
                "source_index": record.get("source_index"),
                "field": "correct_answer",
            }
        ]
    if _coerce_float(record.get("score")) is None:
        warnings.append("total_score_missing")
    if any(point.get("max_score") is None for point in points):
        warnings.append("point_score_missing")
    if any(str(point.get("confidence") or "").startswith("C") for point in points):
        warnings.append("low_confidence_points_require_manual_review")

    payload = {
        "stable_rubric_candidate_id": stable_hash(source_seed, prefix="rub_"),
        "stable_question_source_id": stable_hash(
            f"{source_path}|{record.get('source_chunk_id')}|{record.get('source_index')}",
            prefix="qsrc_",
        ),
        "source_chunk_id": record.get("source_chunk_id"),
        "source_index": record.get("source_index"),
        "question_type": "case_study",
        "node_code": record.get("node_code"),
        "exam_year": record.get("exam_year"),
        "stem_preview": _preview(str(record.get("stem") or ""), 220),
        "total_score": _coerce_float(record.get("score")),
        "answer_hash": content_hash(answer),
        "answer_preview": _preview(answer, 260),
        "scoring_points": points,
        "point_count": len(points),
        "overall_confidence": _overall_confidence(points),
        "review_status": "pending",
        "writeback_policy": "shadow_only_review_required",
        "derivation_scope": "answer_text_only_mvp",
        "warnings": warnings,
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)


def _segment_subquestions(answer: str, total_score: object) -> list[dict[str, Any]]:
    text = _strip_answer_header(answer)
    matches = list(_SUBQUESTION_RE.finditer(text))
    if not matches:
        return [{"subquestion_index": None, "subquestion_score": _coerce_float(total_score), "text": text}]

    segments: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segments.append(
            {
                "subquestion_index": int(match.group(1)),
                "subquestion_score": _coerce_float(match.group(2)),
                "text": text[start:end].strip(),
            }
        )
    return segments


def _extract_points_from_segment(
    text: str,
    *,
    subquestion_index: int | None,
    subquestion_score: float | None,
) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []

    alpha_points = _extract_alpha_points(text, subquestion_index=subquestion_index, subquestion_score=subquestion_score)
    if len(alpha_points) >= 2:
        return alpha_points

    blocks = _extract_parenthesized_blocks(text, subquestion_index=subquestion_index)
    if blocks:
        return _apply_equal_split_if_needed(blocks, subquestion_score)

    circled = _extract_circled_points(text, subquestion_index=subquestion_index)
    if circled:
        return _apply_equal_split_if_needed(circled, subquestion_score)

    semicolon = _extract_semicolon_points(text, subquestion_index=subquestion_index, subquestion_score=subquestion_score)
    if len(semicolon) >= 2:
        return semicolon

    score = _first_score(text)
    return [
        _point(
            label=_remove_score(text),
            expected_answer=_remove_score(text),
            max_score=score or subquestion_score,
            match_type="short_answer",
            confidence="B-" if score is not None else "C",
            derivation_method="single_clause",
            subquestion_index=subquestion_index,
        )
    ]


def _extract_alpha_points(
    text: str,
    *,
    subquestion_index: int | None,
    subquestion_score: float | None,
) -> list[dict[str, Any]]:
    matches = list(_ALPHA_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []
    inferred_score = _equal_score(subquestion_score, len(matches))
    points: list[dict[str, Any]] = []
    for match in matches:
        key = match.group(1)
        value = _clean_clause(match.group(2))
        points.append(
            _point(
                label=f"{key}: {value}",
                expected_answer=value,
                max_score=inferred_score,
                match_type="blank_fill",
                confidence="B+" if inferred_score is not None else "B",
                derivation_method="alpha_blank_split",
                subquestion_index=subquestion_index,
                acceptable_expressions=[value],
            )
        )
    return points


def _extract_parenthesized_blocks(text: str, *, subquestion_index: int | None) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for match in _PAREN_ITEM_RE.finditer(text):
        body = match.group(2).strip()
        circled = _extract_circled_points(body, subquestion_index=subquestion_index)
        if circled:
            points.extend(circled)
            continue
        score = _first_score(body)
        clean = _remove_score(body)
        if _looks_like_diagram_answer(clean):
            confidence = "C"
            match_type = "diagram_or_drawing_answer"
            derivation_method = "parenthesized_item_split+diagram_manual_review"
        else:
            confidence = "A-" if score is not None else "B"
            match_type = "enumeration_or_step"
            derivation_method = "parenthesized_item_split"
        points.append(
            _point(
                label=clean,
                expected_answer=_expected_answer(clean),
                max_score=score,
                match_type=match_type,
                confidence=confidence,
                derivation_method=derivation_method,
                subquestion_index=subquestion_index,
            )
        )
    return points


def _extract_circled_points(text: str, *, subquestion_index: int | None) -> list[dict[str, Any]]:
    pieces = _CIRCLED_SPLIT_RE.split(text)
    if len(pieces) < 3:
        return []
    points: list[dict[str, Any]] = []
    for idx in range(1, len(pieces), 2):
        marker = pieces[idx]
        body = pieces[idx + 1] if idx + 1 < len(pieces) else ""
        body = body.strip()
        if not body:
            continue
        score = _first_score(body)
        clean = _remove_score(body)
        clean = re.split(r"\n\s*[（(]\d+[）)]", clean, maxsplit=1)[0].strip()
        clean = _clean_clause(clean)
        points.append(
            _point(
                label=f"{marker} {clean}",
                expected_answer=_expected_answer(clean),
                max_score=score,
                match_type="enumeration",
                confidence="A-" if score is not None else "B",
                derivation_method="circled_item_split",
                subquestion_index=subquestion_index,
            )
        )
    return points


def _extract_semicolon_points(
    text: str,
    *,
    subquestion_index: int | None,
    subquestion_score: float | None,
) -> list[dict[str, Any]]:
    clauses = [_clean_clause(part) for part in re.split(r"[；;]\s*", _strip_answer_header(text))]
    clauses = [part for part in clauses if len(part) >= 2]
    if len(clauses) < 2:
        return []
    inferred_score = _equal_score(subquestion_score, len(clauses))
    return [
        _point(
            label=clause,
            expected_answer=_expected_answer(clause),
            max_score=inferred_score,
            match_type="parallel_clause",
            confidence="B" if inferred_score is not None else "B-",
            derivation_method="semicolon_split",
            subquestion_index=subquestion_index,
        )
        for clause in clauses
    ]


def _point(
    *,
    label: str,
    expected_answer: str,
    max_score: float | None,
    match_type: str,
    confidence: str,
    derivation_method: str,
    subquestion_index: int | None,
    acceptable_expressions: list[str] | None = None,
) -> dict[str, Any]:
    expected = _clean_clause(expected_answer)
    expressions = acceptable_expressions or _default_acceptable_expressions(expected)
    return {
        "point_id": "",
        "ordinal": 0,
        "subquestion_index": subquestion_index,
        "label": _clean_clause(label),
        "expected_answer": expected,
        "max_score": max_score,
        "match_type": match_type,
        "acceptable_expressions": expressions,
        "common_mistake_candidates": [],
        "confidence": confidence,
        "derivation_method": derivation_method,
        "review_status": "pending",
    }


def _apply_equal_split_if_needed(points: list[dict[str, Any]], total_score: float | None) -> list[dict[str, Any]]:
    if not points:
        return points
    if all(point.get("max_score") is not None for point in points):
        return points
    inferred = _equal_score(total_score, len(points))
    if inferred is None:
        return points
    for point in points:
        if point.get("max_score") is None:
            point["max_score"] = inferred
            point["confidence"] = _downgrade_confidence(str(point.get("confidence") or "B"))
            point["derivation_method"] = f"{point['derivation_method']}+equal_score_inferred"
    return points


def _equal_score(total_score: float | None, count: int) -> float | None:
    if not total_score or count <= 0:
        return None
    value = total_score / count
    return round(value, 2)


def _first_score(text: str) -> float | None:
    match = _SCORE_RE.search(text)
    return _coerce_float(match.group(1)) if match else None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_answer_header(text: str) -> str:
    value = _normalize_escaped_text(str(text or "")).strip()
    value = re.sub(r"^【?参考答案】?\s*", "", value).strip()
    return value


def _remove_score(text: str) -> str:
    return _SCORE_RE.sub("", text).strip()


def _clean_clause(text: str) -> str:
    value = re.sub(r"\s+", " ", _normalize_escaped_text(str(text or ""))).strip()
    value = value.strip("；;。,.， ")
    return value


def _normalize_escaped_text(text: str) -> str:
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def _expected_answer(text: str) -> str:
    value = _clean_clause(text)
    if "：" in value:
        return _clean_clause(value.split("：", 1)[1])
    if ":" in value:
        return _clean_clause(value.split(":", 1)[1])
    return value


def _default_acceptable_expressions(expected: str) -> list[str]:
    expected = _clean_clause(expected)
    if not expected:
        return []
    parts = [_clean_clause(part) for part in re.split(r"[、，,]\s*", expected)]
    parts = [part for part in parts if part]
    if 1 < len(parts) <= 8:
        return sorted({expected, *parts})
    return [expected]


def _downgrade_confidence(value: str) -> str:
    if value.startswith("C"):
        return value
    if value.startswith("A"):
        return "B+"
    if value == "B+":
        return "B"
    return value


def _looks_like_diagram_answer(text: str) -> bool:
    value = str(text or "")
    return "```" in value or "画图" in value or "网络计划图" in value


def _overall_confidence(points: list[dict[str, Any]]) -> str:
    if not points:
        return "D"
    values = [str(point.get("confidence") or "C") for point in points]
    if all(value.startswith("A") or value == "B+" for value in values):
        return "A-"
    if any(value.startswith("C") for value in values):
        return "C"
    return "B"


def _preview(text: str, limit: int) -> str:
    value = _clean_clause(text)
    return value if len(value) <= limit else value[: limit - 1] + "…"
