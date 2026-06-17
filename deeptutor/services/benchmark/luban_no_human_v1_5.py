"""Textbook-anchored, auditable no-human v1.5 golden helpers for Luban grading."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

from deeptutor.services.benchmark.irr_scoring import score_point_label_agreement


TEXTBOOK_DIR_NAME = "2026教材"
_COMPACT_DROP_CHARS = set(" \t\r\n()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’")
JUNK_REQUIRED_TERMS = {"可选项", "近义不算", "每项1分", "算", "或", "如", "分别为"}
JUNK_REQUIRED_TERM_PATTERNS = (
    re.compile(r"^\d+(?:\.\d+)?$"),
    re.compile(r"^\d+[）).、]?$"),
    re.compile(r"^\d+分$"),
    re.compile(r"^[一二三四五六七八九十\d]+项$"),
    re.compile(r".*估计.*分.*"),
    re.compile(r".*满分\d+分.*"),
    re.compile(r".*每项\d+分.*"),
)
SUBSTRING_CONTEXT_RISK_PATTERNS = {
    "厕所": (re.compile(r"上厕所"), re.compile(r"厕所的")),
}


def _clean_required_term(value: Any) -> str:
    text = str(value or "").strip(" \t\r\n,，、;；。.!！?？\"'“”‘’")
    text = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", text)
    text = re.sub(r"^\(?\d+[）).、]\s*", "", text)
    return text.strip(" \t\r\n,，、;；。.!！?？\"'“”‘’")


def _is_junk_required_term(term: str) -> bool:
    text = _clean_required_term(term)
    if not text or text in JUNK_REQUIRED_TERMS:
        return True
    if len(text) < 2:
        return True
    return any(pattern.fullmatch(text) for pattern in JUNK_REQUIRED_TERM_PATTERNS)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compact(value: Any) -> str:
    return re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’]+", "", str(value or ""))


def _compact_with_raw_offsets(value: str) -> tuple[str, list[int]]:
    compact_chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(value):
        if char in _COMPACT_DROP_CHARS or char.isspace():
            continue
        compact_chars.append(char)
        offsets.append(index)
    return "".join(compact_chars), offsets


def _flatten_strings(value: Any, *, pointer: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        text = value.strip()
        return [(pointer or "$", text)] if text else []
    if isinstance(value, list):
        rows: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            rows.extend(_flatten_strings(item, pointer=f"{pointer}/{index}"))
        return rows
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            rows.extend(_flatten_strings(item, pointer=f"{pointer}/{key}"))
        return rows
    return []


def _textbook_json_paths(root: Path) -> list[Path]:
    strengthened_dir = root / TEXTBOOK_DIR_NAME / "第二次加强"
    if strengthened_dir.exists():
        primary = sorted(strengthened_dir.glob("FINAL_CLEANED_BOOK2026-*_fixed.json"))
        if primary:
            return primary
    textbook_dir = root / TEXTBOOK_DIR_NAME
    if not textbook_dir.exists():
        return []
    primary = sorted(textbook_dir.rglob("FINAL_CLEANED_BOOK2026-*_fixed.json"))
    return primary or sorted(textbook_dir.rglob("*.json"))


def _content_markdown_records(payload: Any, *, rel: str, raw_text: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("content_blocks"), list):
        records: list[dict[str, Any]] = []
        for index, block in enumerate(payload.get("content_blocks") or []):
            if not isinstance(block, dict):
                continue
            text = str(block.get("content_markdown") or "").strip()
            if not text:
                continue
            compact_text, compact_offsets = _compact_with_raw_offsets(text)
            taxonomy = block.get("taxonomy") if isinstance(block.get("taxonomy"), dict) else {}
            source_meta = block.get("source_meta") if isinstance(block.get("source_meta"), dict) else {}
            records.append(
                {
                    "source_path": rel,
                    "source_class": "textbook",
                    "json_pointer": f"$.content_blocks[{index}].content_markdown",
                    "text": text,
                    "compact_text": compact_text,
                    "compact_offsets": compact_offsets,
                    "content_hash": _sha256_text(text),
                    "chunk_id": str(block.get("chunk_id") or block.get("id") or ""),
                    "node_code": str(taxonomy.get("node_code") or ""),
                    "node_name": str(taxonomy.get("node_name") or ""),
                    "taxonomy_path": str(taxonomy.get("taxonomy_path") or ""),
                    "page_num": source_meta.get("page_num"),
                    "source_meta": source_meta,
                }
            )
        return records
    return []


def build_textbook_anchor_corpus(source_root: Path) -> list[dict[str, Any]]:
    """Build local exact-search records from faithful textbook content_markdown only."""

    root = Path(source_root).expanduser().resolve()
    records: list[dict[str, Any]] = []
    for path in _textbook_json_paths(root):
        raw_text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root).as_posix()
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            continue
        records.extend(_content_markdown_records(payload, rel=rel, raw_text=raw_text))
    return records


def build_case_official_answer_corpus(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Add official answer as case-local exact anchor source.

    This is still offline gold construction, not RAG and not runtime grading.
    """

    case_id = str(case.get("case_id") or "unknown")
    text = str(case.get("official_answer") or "").strip()
    if not text:
        return []
    compact_text, compact_offsets = _compact_with_raw_offsets(text)
    return [
        {
            "source_path": f"golden/{case_id}/official_answer",
            "source_class": "official_answer",
            "json_pointer": "$.official_answer",
            "text": text,
            "compact_text": compact_text,
            "compact_offsets": compact_offsets,
            "content_hash": _sha256_text(text),
        }
    ]


def build_case_exam_figure_corpus(case: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = str(case.get("case_id") or "unknown")
    text = "\n".join(str(case.get(field) or "").strip() for field in ("stem", "official_answer") if case.get(field)).strip()
    if not text:
        return []
    compact_text, compact_offsets = _compact_with_raw_offsets(text)
    return [
        {
            "source_path": f"golden/{case_id}/exam_figure_and_official_answer",
            "source_class": "exam_figure",
            "json_pointer": "$.stem + $.official_answer",
            "text": text,
            "compact_text": compact_text,
            "compact_offsets": compact_offsets,
            "content_hash": _sha256_text(text),
            "chunk_id": "",
            "node_code": str(case.get("question_node") or ""),
            "page_num": None,
        }
    ]


def _exact_anchor(term: str, record: dict[str, Any]) -> dict[str, Any] | None:
    text = str(record.get("text") or "")
    start = text.find(term)
    if start < 0:
        return None
    end = start + len(term)
    return {
        "source_path": record["source_path"],
        "source_class": record["source_class"],
        "json_pointer": record["json_pointer"],
        "chunk_id": record.get("chunk_id") or "",
        "node_code": record.get("node_code") or "",
        "page_num": record.get("page_num"),
        "start": start,
        "end": end,
        "span_text": text[start:end],
        "match_method": "exact",
        "content_hash": record["content_hash"],
    }


def _form_normalized_anchor(term: str, record: dict[str, Any]) -> dict[str, Any] | None:
    text = str(record.get("text") or "")
    compact_term = _compact(term)
    compact_text = str(record.get("compact_text") or "")
    offsets = list(record.get("compact_offsets") or [])
    compact_start = compact_text.find(compact_term) if compact_term else -1
    if compact_start < 0 or compact_start >= len(offsets):
        return None
    compact_end = compact_start + len(compact_term) - 1
    if compact_end >= len(offsets):
        return None
    raw_start = int(offsets[compact_start])
    raw_end = int(offsets[compact_end]) + 1
    return {
        "source_path": record["source_path"],
        "source_class": record["source_class"],
        "json_pointer": record["json_pointer"],
        "chunk_id": record.get("chunk_id") or "",
        "node_code": record.get("node_code") or "",
        "page_num": record.get("page_num"),
        "start": raw_start,
        "end": raw_end,
        "span_text": text[raw_start:raw_end],
        "match_method": "form_normalized",
        "content_hash": record["content_hash"],
    }


def anchor_required_terms(terms: list[str], corpus: list[dict[str, Any]], *, max_anchors: int = 2) -> dict[str, Any]:
    anchored: list[dict[str, Any]] = []
    unanchored: list[str] = []
    for raw_term in terms:
        term = str(raw_term or "").strip()
        if not term:
            continue
        primary_anchors: list[dict[str, Any]] = []
        weak_anchors: list[dict[str, Any]] = []
        for record in corpus:
            exact = _exact_anchor(term, record)
            if exact:
                target = weak_anchors if exact.get("source_class") == "official_answer" else primary_anchors
                target.append(exact)
                if len(primary_anchors) >= max_anchors:
                    break
        if not primary_anchors and not weak_anchors:
            for record in corpus:
                normalized = _form_normalized_anchor(term, record)
                if normalized:
                    target = weak_anchors if normalized.get("source_class") == "official_answer" else primary_anchors
                    target.append(normalized)
                    if len(primary_anchors) >= max_anchors:
                        break
        anchors = primary_anchors[:max_anchors] if primary_anchors else weak_anchors[:max_anchors]
        anchored.append({"term": term, "anchors": anchors})
        if not anchors:
            unanchored.append(term)
    return {"terms": anchored, "unanchored_terms": unanchored}


def categorize_unanchored_term(term: str, corpus: list[dict[str, Any]]) -> dict[str, Any]:
    text = str(term or "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:kg|万|万元|天|人|m|mm|%)", text, flags=re.I):
        return {"term": text, "category": "is_numeric_not_term", "repair_terms": []}
    anchors = anchor_required_terms([text], corpus).get("terms") or []
    if anchors and anchors[0].get("anchors"):
        method = str(anchors[0]["anchors"][0].get("match_method") or "")
        category = "normalization_miss" if method == "form_normalized" else "in_standard_not_textbook"
        return {"term": text, "category": category, "repair_terms": [text]}
    if "/" in text or "／" in text:
        repaired = []
        for item in re.split(r"[/／]", text):
            item = item.strip()
            if item and (anchor_required_terms([item], corpus).get("terms") or [{}])[0].get("anchors"):
                repaired.append(item)
        repaired = [
            item
            for item in repaired
            if not any(_compact(item) and _compact(item) in _compact(other) and item != other for other in repaired)
        ]
        if repaired:
            return {"term": text, "category": "rubric_is_paraphrase", "repair_terms": repaired}
    if len(text) > 14 or re.search(r"不妥|应|不得|可选项|合并理解|正确做法|先|再|其中", text):
        repaired = _anchored_subterms(text, corpus)
        return {"term": text, "category": "rubric_is_paraphrase", "repair_terms": repaired}
    return {"term": text, "category": "genuinely_absent", "repair_terms": []}


def _anchored_subterms(term: str, corpus: list[dict[str, Any]]) -> list[str]:
    candidates: list[str] = []
    for raw in re.split(r"[:：,，;；。/／、\s]+", str(term or "")):
        raw = _clean_required_term(re.split(r"[（(]", raw.strip("（）()[]【】"), 1)[0])
        if 2 <= len(raw) <= 16:
            candidates.append(raw)
    for match in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9（）()、-]{2,16}", str(term or "")):
        candidates.append(_clean_required_term(match.group(0).strip("（）()")))
    seen: set[str] = set()
    repaired: list[str] = []
    for candidate in candidates:
        if _is_junk_required_term(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        anchored = anchor_required_terms([candidate], corpus).get("terms") or []
        if anchored and anchored[0].get("anchors"):
            if any(_compact(candidate) and _compact(candidate) in _compact(other) and candidate != other for other in repaired):
                continue
            repaired.append(candidate)
    return repaired


def squeeze_required_terms(terms: list[str], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    squeezed: list[str] = []
    repairs: list[dict[str, Any]] = []
    root_counts: dict[str, int] = {}
    for raw_term in terms:
        term = _clean_required_term(raw_term)
        if not term:
            continue
        if _is_junk_required_term(term):
            repairs.append({"term": term, "category": "junk_non_term", "repair_terms": [], "original_term": term})
            root_counts["junk_non_term"] = root_counts.get("junk_non_term", 0) + 1
            continue
        anchored = anchor_required_terms([term], corpus).get("terms") or []
        if anchored and anchored[0].get("anchors"):
            squeezed.append(term)
            continue
        category = categorize_unanchored_term(term, corpus)
        root = str(category["category"])
        root_counts[root] = root_counts.get(root, 0) + 1
        repair_terms = list(category.get("repair_terms") or [])
        repairs.append({**category, "original_term": term})
        squeezed.extend(repair_terms)
    unique: list[str] = []
    seen_compact: set[str] = set()
    for term in squeezed:
        compact = _compact(term)
        if not compact or compact in seen_compact or _is_junk_required_term(term):
            continue
        seen_compact.add(compact)
        unique.append(term)
    return {
        "terms": unique,
        "repairs": repairs,
        "root_cause_counts": dict(sorted(root_counts.items())),
    }


def numeric_terms_from_point(point: dict[str, Any]) -> list[str]:
    expected = [str(term).strip() for term in point.get("calculation_expected_terms_v1_5") or [] if str(term).strip()]
    if expected:
        return expected
    text = f"{point.get('label') or ''}\n{point.get('official_basis') or ''}"
    seen: set[str] = set()
    terms: list[str] = []
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(kg|万|万元|天|人|名|个月|m|mm|%)", text, flags=re.I):
        term = f"{value}{unit}"
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _matched_terms(answer_text: str, terms: list[str]) -> list[str]:
    compact_answer = _compact(answer_text)
    return [term for term in terms if _compact(term) and _compact(term) in compact_answer]


def _context_risk_terms(answer_text: str, matched_terms: list[str]) -> list[str]:
    risks: list[str] = []
    for term in matched_terms:
        for pattern in SUBSTRING_CONTEXT_RISK_PATTERNS.get(str(term), ()):
            if pattern.search(str(answer_text or "")):
                risks.append(str(term))
                break
    return risks


def _hit_from_ratio(matched_count: int, total_count: int) -> str:
    if total_count <= 0 or matched_count <= 0:
        return "miss"
    if matched_count == total_count:
        return "hit"
    return "partial"


def judge_point_agent_a(answer_text: str, terms: list[str], *, max_score: float) -> dict[str, Any]:
    matched = _matched_terms(answer_text, terms)
    score = float(max_score or 0) * (len(matched) / len(terms)) if terms else 0.0
    return {
        "agent": "A",
        "hit": _hit_from_ratio(len(matched), len(terms)),
        "score": round(score, 4),
        "matched_terms": matched,
    }


def judge_point_agent_b(answer_text: str, terms: list[str], *, max_score: float) -> dict[str, Any]:
    compact_answer = _compact(answer_text)
    matched: list[str] = []
    for term in terms:
        compact_term = _compact(term)
        if compact_term and compact_answer.find(compact_term) >= 0:
            matched.append(term)
    score = float(max_score or 0) * (len(matched) / len(terms)) if terms else 0.0
    return {
        "agent": "B",
        "hit": _hit_from_ratio(len(matched), len(terms)),
        "score": round(score, 4),
        "matched_terms": matched,
    }


def _residual_type(point: dict[str, Any], terms: list[str], unanchored_terms: list[str]) -> str:
    text = f"{point.get('label') or ''}\n{point.get('official_basis') or ''}\n{point.get('list_rule') or ''}"
    if re.search(r"计算|工期|费用|价款|索赔|流水|网络计划|关键线路|=", text):
        return "calculation"
    if re.search(r"是否|妥当|不妥|正确做法|判断", text):
        return "judgment"
    if point.get("boundary") or unanchored_terms or not terms:
        return "boundary"
    return ""


def classify_residual_resolution(
    *,
    residual_type: str,
    unanchored_terms: list[str],
    terms: list[str],
    matched_terms: list[str],
) -> dict[str, str]:
    """Route residual work through Tier-0, then Tier-1, with Tier-2 as last resort."""

    residual = str(residual_type or "").strip()
    if not residual:
        return {
            "resolution_class": "A",
            "resolution_label": "Tier-0 automatic literal-term certification",
            "exhaustion_proof": "",
        }
    if residual == "calculation":
        return {
            "resolution_class": "A",
            "resolution_label": "Tier-0 deterministic numeric validation",
            "exhaustion_proof": "",
        }
    if residual == "judgment" and terms:
        return {
            "resolution_class": "A",
            "resolution_label": "Tier-0 judgment resolved by literal judgment wording plus textbook terms",
            "exhaustion_proof": "",
        }
    if residual == "expert_discretion":
        return {
            "resolution_class": "C",
            "resolution_label": "Tier-2 external expert last resort",
            "exhaustion_proof": "Tier-0 cannot anchor or deterministically validate this item, and Tier-1 cannot decide from textbook provenance plus official answer; only external expert scoring discretion remains.",
        }
    if residual in {"boundary", "judgment"} or unanchored_terms:
        return {
            "resolution_class": "B",
            "resolution_label": "Tier-1 PO self-decision from textbook excerpt and official answer",
            "exhaustion_proof": "Tier-0 exposed a boundary or unanchored term; a careful PO can decide by reading the pinned source and official answer, so Tier-2 is not justified.",
        }
    return {
        "resolution_class": "C",
        "resolution_label": "Tier-2 external expert last resort",
        "exhaustion_proof": "Tier-0 cannot anchor or deterministically validate this item, and Tier-1 cannot decide from textbook provenance plus official answer; only external expert scoring discretion remains.",
    }


def _label_for_point(
    *,
    case_id: str,
    sample_id: str,
    point: dict[str, Any],
    answer_text: str,
    terms: list[str],
    unanchored_terms: list[str],
) -> dict[str, Any]:
    max_score = float(point.get("max_score") or 0)
    if point.get("anchor_source") in {"non_textbook", "official_answer_weak"} and not terms:
        resolution = classify_residual_resolution(
            residual_type="boundary",
            unanchored_terms=[str(point.get("anchor_source"))],
            terms=[],
            matched_terms=[],
        )
        agent = {"hit": "unverifiable", "score": None, "matched_terms": []}
        return {
            "case_id": case_id,
            "sample_id": sample_id,
            "point_id": str(point.get("point_id") or ""),
            "max_score": max_score,
            "verifiable": False,
            "is_deterministic": False,
            "residual_type": "boundary",
            "resolution_class": resolution["resolution_class"],
            "resolution_label": "Tier-1 required: point is not certified by content_markdown textbook anchors",
            "exhaustion_proof": "This point is outside verified content_markdown textbook-term certification; it must not be auto-certified from official-answer weak anchors or non-textbook knowledge.",
            "agent_a": {"agent": "A", **agent},
            "agent_b": {"agent": "B", **agent},
            "hit": "unverifiable",
            "score": None,
            "matched_terms": [],
            "unanchored_terms": [str(point.get("anchor_source"))],
            "numeric_terms": [],
        }
    residual_type = _residual_type(point, terms, unanchored_terms)
    numeric_terms = numeric_terms_from_point(point)
    effective_terms = numeric_terms if residual_type == "calculation" and numeric_terms else terms
    effective_unanchored_terms = [] if residual_type == "calculation" and numeric_terms else unanchored_terms
    if not effective_terms:
        unresolved_residual = residual_type or "boundary"
        resolution = classify_residual_resolution(
            residual_type=unresolved_residual,
            unanchored_terms=effective_unanchored_terms or ["no_verifiable_required_terms"],
            terms=[],
            matched_terms=[],
        )
        agent = {"hit": "unverifiable", "score": None, "matched_terms": []}
        return {
            "case_id": case_id,
            "sample_id": sample_id,
            "point_id": str(point.get("point_id") or ""),
            "max_score": max_score,
            "verifiable": False,
            "is_deterministic": False,
            "residual_type": unresolved_residual,
            "resolution_class": resolution["resolution_class"],
            "resolution_label": "Tier-1 required: no verifiable official terms after exact anchoring",
            "exhaustion_proof": "No exact official-answer/textbook/standard anchor terms are available; offline gold builder must not certify this as a deterministic miss.",
            "agent_a": {"agent": "A", **agent},
            "agent_b": {"agent": "B", **agent},
            "hit": "unverifiable",
            "score": None,
            "matched_terms": [],
            "unanchored_terms": effective_unanchored_terms or ["no_verifiable_required_terms"],
            "numeric_terms": numeric_terms,
        }
    a = judge_point_agent_a(answer_text, effective_terms, max_score=max_score)
    b = judge_point_agent_b(answer_text, effective_terms, max_score=max_score)
    context_risks = _context_risk_terms(answer_text, list(a.get("matched_terms") or []))
    if context_risks:
        resolution = classify_residual_resolution(
            residual_type="boundary",
            unanchored_terms=context_risks,
            terms=effective_terms,
            matched_terms=list(a.get("matched_terms") or []),
        )
        return {
            "case_id": case_id,
            "sample_id": sample_id,
            "point_id": str(point.get("point_id") or ""),
            "max_score": max_score,
            "verifiable": False,
            "is_deterministic": False,
            "residual_type": "boundary",
            "resolution_class": resolution["resolution_class"],
            "resolution_label": "Tier-1 required: substring context risk, not literal-term certification",
            "exhaustion_proof": "The answer only contains a risky substring context for an official term; no-human certification must defer to PO review instead of auto-awarding.",
            "agent_a": a,
            "agent_b": b,
            "hit": "unverifiable",
            "score": None,
            "matched_terms": list(a.get("matched_terms") or []),
            "unanchored_terms": effective_unanchored_terms,
            "numeric_terms": numeric_terms,
            "context_risk_terms": context_risks,
        }
    is_deterministic = bool(effective_terms) and not effective_unanchored_terms and residual_type in {"", "calculation", "judgment"}
    resolution = classify_residual_resolution(
        residual_type="" if is_deterministic else (residual_type or "boundary"),
        unanchored_terms=effective_unanchored_terms,
        terms=effective_terms,
        matched_terms=a["matched_terms"],
    )
    adjudicated = a if a == b else {"hit": a["hit"], "score": a["score"], "matched_terms": a["matched_terms"]}
    return {
        "case_id": case_id,
        "sample_id": sample_id,
        "point_id": str(point.get("point_id") or ""),
        "max_score": max_score,
        "verifiable": True,
        "is_deterministic": is_deterministic,
        "residual_type": "" if is_deterministic else (residual_type or "boundary"),
        "resolution_class": resolution["resolution_class"],
        "resolution_label": resolution["resolution_label"],
        "exhaustion_proof": resolution["exhaustion_proof"],
        "agent_a": a,
        "agent_b": b,
        "hit": adjudicated["hit"],
        "score": round(float(adjudicated["score"]), 4),
        "matched_terms": adjudicated["matched_terms"],
        "unanchored_terms": effective_unanchored_terms,
        "numeric_terms": numeric_terms,
    }


def build_no_human_labels_for_case(
    *,
    case: dict[str, Any],
    corpus: list[dict[str, Any]],
    required_terms_by_point: dict[str, list[str]],
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    point_provenance: dict[str, dict[str, Any]] = {}
    labels_a: list[dict[str, Any]] = []
    labels_b: list[dict[str, Any]] = []
    adjudicated_labels: dict[str, list[dict[str, Any]]] = {}
    for point in case.get("gold_scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        terms = required_terms_by_point.get(point_id, [])
        point_provenance[point_id] = anchor_required_terms(terms, corpus)
    for sample in case.get("eval_samples") or []:
        sample_id = str(sample.get("student_id") or "")
        sample_labels: list[dict[str, Any]] = []
        answer_text = str(sample.get("answer_text") or "")
        for point in case.get("gold_scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            terms = required_terms_by_point.get(point_id, [])
            provenance = point_provenance[point_id]
            label = _label_for_point(
                case_id=case_id,
                sample_id=sample_id,
                point=point,
                answer_text=answer_text,
                terms=terms,
                unanchored_terms=list(provenance.get("unanchored_terms") or []),
            )
            labels_a.append({**label["agent_a"], "case_id": case_id, "sample_id": sample_id, "point_id": point_id})
            labels_b.append({**label["agent_b"], "case_id": case_id, "sample_id": sample_id, "point_id": point_id})
            sample_labels.append(label)
        adjudicated_labels[sample_id] = sample_labels
    return {
        "point_provenance": point_provenance,
        "labels_by_sample": adjudicated_labels,
        "agent_agreement": score_point_label_agreement(labels_a, labels_b),
    }


def summarize_no_human_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    labels = [
        label
        for case in fixture.get("cases") or []
        for sample in case.get("eval_samples") or []
        for label in sample.get("no_human_v1_5_labels") or []
    ]
    deterministic = [label for label in labels if label.get("is_deterministic")]
    residual = [label for label in labels if not label.get("is_deterministic")]
    residual_counts: dict[str, int] = {}
    resolution_counts: dict[str, int] = {}
    for label in residual:
        key = str(label.get("residual_type") or "unknown")
        residual_counts[key] = residual_counts.get(key, 0) + 1
    for label in labels:
        key = str(label.get("resolution_class") or "unknown")
        resolution_counts[key] = resolution_counts.get(key, 0) + 1
    return {
        "cases": len(fixture.get("cases") or []),
        "samples": sum(len(case.get("eval_samples") or []) for case in fixture.get("cases") or []),
        "point_labels": len(labels),
        "deterministic_point_labels": len(deterministic),
        "deterministic_ratio": round(len(deterministic) / len(labels), 4) if labels else 0.0,
        "residual_point_labels": len(residual),
        "residual_counts": dict(sorted(residual_counts.items())),
        "resolution_counts": dict(sorted(resolution_counts.items())),
        "po_workload_ratio": round(resolution_counts.get("B", 0) / len(labels), 4) if labels else 0.0,
        "external_expert_necessity_ratio": round(resolution_counts.get("C", 0) / len(labels), 4) if labels else 0.0,
        "mean_deterministic_score": round(mean([float(label.get("score") or 0) for label in deterministic]), 4)
        if deterministic
        else 0.0,
    }


def build_human_escalation_queues(fixture: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    queues = {"R7a_PO_self_decision": [], "R7b_external_expert_last_resort": []}
    for case in fixture.get("cases") or []:
        points = {str(point.get("point_id") or ""): point for point in case.get("gold_scoring_points") or []}
        for sample in case.get("eval_samples") or []:
            for label in sample.get("no_human_v1_5_labels") or []:
                klass = str(label.get("resolution_class") or "")
                if klass not in {"B", "C"}:
                    continue
                point = points.get(str(label.get("point_id"))) or {}
                row = {
                    "case_id": case.get("case_id"),
                    "sample_id": sample.get("student_id"),
                    "point_id": label.get("point_id"),
                    "resolution_class": klass,
                    "question_stem": case.get("stem"),
                    "official_answer": case.get("official_answer"),
                    "point_label": point.get("label"),
                    "official_basis": point.get("official_basis"),
                    "student_answer": sample.get("answer_text"),
                    "unanchored_terms": label.get("unanchored_terms") or [],
                    "exhaustion_proof": label.get("exhaustion_proof") or "",
                    "estimated_review_seconds": 30 if klass == "C" else 60,
                }
                target = "R7a_PO_self_decision" if klass == "B" else "R7b_external_expert_last_resort"
                queues[target].append(row)
    return queues


def _resolution_label_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    return {
        (str(row.get("case_id")), str(row.get("sample_id")), str(row.get("point_id"))): str(row.get("resolution_class") or "")
        for row in rows
    }


def merge_independent_resolution_labels(
    queue: list[dict[str, Any]],
    labels_a: list[dict[str, Any]],
    labels_b: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge true independent A/B residual triage.

    Only A/A agreement demotes to class A. Any disagreement stays class B unless
    either side says C, in which case it is surfaced as C with evidence.
    """

    a_map = _resolution_label_map(labels_a)
    b_map = _resolution_label_map(labels_b)
    rows: list[dict[str, Any]] = []
    counts = {"A": 0, "B": 0, "C": 0}
    for item in queue:
        key = (str(item.get("case_id")), str(item.get("sample_id")), str(item.get("point_id")))
        a_class = a_map.get(key, "")
        b_class = b_map.get(key, "")
        if a_class == "A" and b_class == "A":
            klass = "A"
        elif a_class == "C" or b_class == "C":
            klass = "C"
        else:
            klass = "B"
        counts[klass] += 1
        rows.append({**item, "agent_a_class": a_class, "agent_b_class": b_class, "resolution_class": klass})
    return {"counts": counts, "rows": rows}


def apply_resolution_merge_to_fixture(fixture: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    merged_classes = {
        (str(row.get("case_id")), str(row.get("sample_id")), str(row.get("point_id"))): str(row.get("resolution_class") or "")
        for row in merged.get("rows") or []
    }
    output = dict(fixture)
    cases: list[dict[str, Any]] = []
    for case in fixture.get("cases") or []:
        case_copy = dict(case)
        samples: list[dict[str, Any]] = []
        for sample in case.get("eval_samples") or []:
            sample_copy = dict(sample)
            labels: list[dict[str, Any]] = []
            for label in sample.get("no_human_v1_5_labels") or []:
                label_copy = dict(label)
                key = (str(case.get("case_id")), str(sample.get("student_id")), str(label.get("point_id")))
                klass = merged_classes.get(key)
                if klass:
                    if label_copy.get("verifiable") is False and klass == "A":
                        labels.append(label_copy)
                        continue
                    label_copy["resolution_class"] = klass
                    label_copy["independent_triage_applied"] = True
                    if klass == "A":
                        label_copy["is_deterministic"] = True
                        label_copy["residual_type"] = ""
                        label_copy["resolution_label"] = "Tier-0 automatic after independent A/B residual triage"
                        label_copy["exhaustion_proof"] = ""
                    elif klass == "C":
                        label_copy["is_deterministic"] = False
                labels.append(label_copy)
            sample_copy["no_human_v1_5_labels"] = labels
            samples.append(sample_copy)
        case_copy["eval_samples"] = samples
        cases.append(case_copy)
    output["cases"] = cases
    return output
