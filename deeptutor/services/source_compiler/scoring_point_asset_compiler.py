from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any

from deeptutor.services.source_compiler.schema import content_hash, stable_hash


SCHEMA_VERSION = "luban_scoring_point_assets.v0.1"

TEXT_TERM_TYPES = {"normative_rule", "text_concept", "definition", "causal_principle"}
CALCULATION_TYPES = {"rule_numeric"}
TABLE_TYPES = {"table_data"}
PROCESS_TYPES = {"process_flow"}

SHORT_COMMON_TERMS = {
    "保护",
    "限制",
    "防护",
    "环境",
    "勘察",
    "浇筑",
    "验收",
    "检查",
    "资料",
    "围挡",
    "施工",
    "设计",
    "监理",
    "安全",
    "质量",
    "材料",
    "管理",
    "控制",
    "记录",
    "文件",
}

STOP_TOKENS = {
    "可选项",
    "图中",
    "须含",
    "包括",
    "规定",
    "要求",
    "内容",
    "措施",
    "标准",
}


def normalize_for_match(value: str) -> str:
    return re.sub(r"[\s　,，.。;；:：、（）()【】\[\]《》<>“”\"'‘’—\-_/|+=*]+", "", value or "")


def normalized_contains(content: str, term: str) -> bool:
    needle = normalize_for_match(term)
    return bool(needle) and needle in normalize_for_match(content)


def _text_len(value: str) -> int:
    return len(normalize_for_match(value))


def _is_short_common(term: str) -> bool:
    normalized = normalize_for_match(term)
    return _text_len(term) <= 3 and (normalized in SHORT_COMMON_TERMS or len(normalized) <= 1)


def _clean_term(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = text.replace("**", "")
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^\*+|\*+$", "", text).strip()
    text = re.sub(r"^[-•]\s*", "", text)
    text = re.sub(r"^[（(]?\d+[）).、]\s*", "", text)
    text = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", text)
    text = text.strip(" ：:；;，,。.!！?？、")
    return text


def _grading_keywords(chunk: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for container in (chunk.get("assessment"), chunk.get("exam_matrix")):
        if isinstance(container, dict):
            raw = container.get("grading_keywords")
            if isinstance(raw, list):
                values.extend(str(item).strip() for item in raw if str(item).strip())
    return values


def _chunk_content(chunk: dict[str, Any]) -> str:
    return str(chunk.get("content_markdown") or "")


def _chunk_id(chunk: dict[str, Any]) -> str:
    return str(chunk.get("chunk_id") or "").strip()


def _node_code(chunk: dict[str, Any]) -> str:
    taxonomy = chunk.get("taxonomy") if isinstance(chunk.get("taxonomy"), dict) else {}
    return str(taxonomy.get("node_code") or "UNKNOWN").strip() or "UNKNOWN"


def _page_num(chunk: dict[str, Any]) -> int | None:
    source_meta = chunk.get("source_meta") if isinstance(chunk.get("source_meta"), dict) else {}
    value = source_meta.get("page_num")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sentence_candidates(content: str) -> list[str]:
    stripped = content.replace(" | ", "\n")
    raw_parts: list[str] = []
    for line in stripped.splitlines():
        original_line = line.strip()
        if original_line.startswith("#"):
            continue
        if original_line.startswith("**") and original_line.endswith("**"):
            continue
        line = _clean_term(re.sub(r"^#+\s*", "", line))
        if not line:
            continue
        if line.startswith("|"):
            continue
        parts = re.split(r"[。；;]\s*", line)
        raw_parts.extend(parts)
    candidates: list[str] = []
    for part in raw_parts:
        part = _clean_term(part)
        if not part or _text_len(part) < 4:
            continue
        if _text_len(part) > 90:
            continue
        candidates.append(part)
    return candidates


def _bold_candidates(content: str) -> list[str]:
    candidates: list[str] = []
    for match in re.findall(r"\*\*([^*]{2,80})\*\*", content or ""):
        term = _clean_term(match)
        if "相关规定" in term or term.endswith("规定"):
            continue
        candidates.append(term)
    return candidates


def _table_candidates(content: str) -> list[str]:
    candidates: list[str] = []
    for line in (content or "").splitlines():
        if "|" not in line:
            continue
        if re.fullmatch(r"[\s|:：\\-]+", line):
            continue
        cells = [_clean_term(cell) for cell in line.split("|")]
        for cell in cells:
            if not cell or re.fullmatch(r"[\d.]+", cell):
                continue
            if 4 <= _text_len(cell) <= 50:
                candidates.append(cell)
    return candidates


def _process_candidates(content: str) -> list[str]:
    pieces = re.split(r"(?:→|->|=>|⇒|；|;|。|\\n)", content or "")
    return [_clean_term(piece) for piece in pieces if 4 <= _text_len(_clean_term(piece)) <= 60]


def _numeric_values(content: str) -> list[str]:
    pattern = re.compile(
        r"(?<![A-Za-z0-9.])(?:±)?\d+(?:\.\d+)?\s*(?:kg|t|m³|m3|m2|㎡|m|mm|cm|MPa|kN|N|%|d|h|天|月|年|人|万元|元|℃|°C)(?![A-Za-z0-9.])"
    )
    values: list[str] = []
    for match in pattern.finditer(content or ""):
        values.append(match.group(0).replace(" ", ""))
    return _dedupe(values)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_for_match(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _expand_short_common(term: str, content: str) -> str | None:
    normalized_term = normalize_for_match(term)
    for sentence in _sentence_candidates(content):
        if normalized_term and normalized_term in normalize_for_match(sentence) and not _is_short_common(sentence):
            return sentence
    return None


def _candidate_terms(chunk: dict[str, Any], *, counters: Counter[str]) -> list[tuple[str, str]]:
    content = _chunk_content(chunk)
    content_type = str(chunk.get("content_type") or "")
    candidates: list[tuple[str, str]] = []

    for keyword in _grading_keywords(chunk):
        counters["seed_total"] += 1
        if normalized_contains(content, keyword):
            counters["seed_hit"] += 1
            candidates.append((_clean_term(keyword), "grading_keyword_seed_verified"))
        else:
            counters["seed_miss"] += 1

    if content_type in TABLE_TYPES:
        candidates.extend((term, "content_table_cell") for term in _table_candidates(content))
    elif content_type in PROCESS_TYPES:
        candidates.extend((term, "content_process_step") for term in _process_candidates(content))
    else:
        candidates.extend((term, "content_bold") for term in _bold_candidates(content))
        candidates.extend((term, "content_sentence") for term in _sentence_candidates(content))

    return [(term, source) for term, source in _dedupe_pairs(candidates) if term]


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for term, source in values:
        key = normalize_for_match(term)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append((term, source))
    return result


def _valid_textbook_anchor(term: str, chunk: dict[str, Any]) -> bool:
    return bool(_chunk_id(chunk)) and normalized_contains(_chunk_content(chunk), term)


def _point_id(run_id: str, chunk: dict[str, Any], term: str, point_type: str) -> str:
    seed = "|".join([run_id, _chunk_id(chunk), _node_code(chunk), point_type, normalize_for_match(term)])
    return stable_hash(seed, prefix="sp_", length=20)


def _asset_row(
    *,
    chunk: dict[str, Any],
    term: str,
    point_type: str,
    source_path: str,
    run_id: str,
    compiled_at: str,
    candidate_source: str,
    calculation_values: list[str] | None = None,
) -> dict[str, Any]:
    chunk_id = _chunk_id(chunk)
    content = _chunk_content(chunk)
    row = {
        "schema_version": SCHEMA_VERSION,
        "version_id": run_id,
        "compiled_at": compiled_at,
        "source_path": source_path,
        "node_code": _node_code(chunk),
        "chunk_id": chunk_id,
        "page_num": _page_num(chunk),
        "point_id": _point_id(run_id, chunk, term, point_type),
        "point_type": point_type,
        "anchor_source": "calculation" if point_type == "calculation" else "textbook",
        "required_terms": [] if point_type == "calculation" else [term],
        "label": term,
        "max_score": None,
        "score_status": "pending_calibration_not_official",
        "candidate_source": candidate_source,
        "provenance": {
            "chunk_id": chunk_id,
            "content_hash": content_hash(content),
            "quote": term if point_type != "calculation" else "",
            "anchor_verified": point_type == "calculation" or _valid_textbook_anchor(term, chunk),
        },
    }
    if point_type == "calculation":
        row["calculation"] = {
            "expected_values": calculation_values or [],
            "verification_mode": "deterministic_recalculation_required",
        }
    else:
        row["list_rule"] = {
            "mode": "term_exact_match",
            "term_count": 1,
            "requires_distinctive_terms": True,
        }
    return row


def compile_scoring_point_assets(
    chunks: list[dict[str, Any]],
    *,
    run_id: str,
    source_path: str,
    compiled_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    point_type_counts: Counter[str] = Counter()
    anchor_source_counts: Counter[str] = Counter()
    node_counts: Counter[str] = Counter()
    discarded: Counter[str] = Counter()

    for chunk in chunks:
        content_type = str(chunk.get("content_type") or "")
        content = _chunk_content(chunk)
        if content_type in CALCULATION_TYPES:
            values = _numeric_values(content)
            if not values:
                discarded["calculation_without_numeric_value"] += 1
                continue
            label = "；".join(values[:4])
            row = _asset_row(
                chunk=chunk,
                term=label,
                point_type="calculation",
                source_path=source_path,
                run_id=run_id,
                compiled_at=compiled_at,
                candidate_source="content_numeric_expression",
                calculation_values=values,
            )
            rows.append(row)
            point_type_counts[row["point_type"]] += 1
            anchor_source_counts[row["anchor_source"]] += 1
            node_counts[row["node_code"]] += 1
            continue

        if content_type in PROCESS_TYPES:
            default_point_type = "process_step"
        elif content_type in TABLE_TYPES:
            default_point_type = "table_term"
        elif content_type in TEXT_TERM_TYPES:
            default_point_type = "text_term"
        else:
            default_point_type = "text_term"

        for term, candidate_source in _candidate_terms(chunk, counters=counters):
            if term in STOP_TOKENS:
                discarded["stop_token"] += 1
                continue
            if _is_short_common(term):
                expanded = _expand_short_common(term, content)
                if not expanded:
                    discarded["short_common_unexpanded"] += 1
                    continue
                term = expanded
                candidate_source = f"{candidate_source}:expanded_from_short_common"
            if not _valid_textbook_anchor(term, chunk):
                if not _chunk_id(chunk):
                    discarded["empty_chunk_id"] += 1
                else:
                    discarded["not_in_content_markdown"] += 1
                continue
            row = _asset_row(
                chunk=chunk,
                term=term,
                point_type=default_point_type,
                source_path=source_path,
                run_id=run_id,
                compiled_at=compiled_at,
                candidate_source=candidate_source,
            )
            rows.append(row)
            point_type_counts[row["point_type"]] += 1
            anchor_source_counts[row["anchor_source"]] += 1
            node_counts[row["node_code"]] += 1

    invalid_textbook = [
        row
        for row in rows
        if row["anchor_source"] == "textbook"
        and (not row["chunk_id"] or not row["provenance"].get("anchor_verified"))
    ]
    loose_anchor = [
        row
        for row in rows
        if row["point_type"] != "calculation"
        and len(row.get("required_terms") or []) == 1
        and _is_short_common(str(row["required_terms"][0]))
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "version_id": run_id,
        "source_path": source_path,
        "chunk_count": len(chunks),
        "asset_count": len(rows),
        "node_count": len(node_counts),
        "point_type_counts": dict(sorted(point_type_counts.items())),
        "anchor_source_counts": dict(sorted(anchor_source_counts.items())),
        "discarded_candidates": dict(sorted(discarded.items())),
        "seed_total": counters["seed_total"],
        "seed_hit": counters["seed_hit"],
        "seed_miss": counters["seed_miss"],
        "seed_hit_rate": counters["seed_hit"] / counters["seed_total"] if counters["seed_total"] else None,
        "invalid_textbook_anchor_count": len(invalid_textbook),
        "loose_anchor_violation_count": len(loose_anchor),
        "quality_gate": "pass" if not invalid_textbook and not loose_anchor else "fail",
        "content_hash": hashlib.sha256(
            "\n".join(row["point_id"] + row["provenance"]["content_hash"] for row in rows).encode("utf-8")
        ).hexdigest(),
    }
    return rows, report


def group_chunks_by_node(chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        grouped[_node_code(chunk)].append(chunk)
    return dict(sorted(grouped.items()))
