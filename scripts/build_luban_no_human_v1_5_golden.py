#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.luban_no_human_v1_5 import (  # noqa: E402
    apply_resolution_merge_to_fixture,
    _anchored_subterms,
    _clean_required_term,
    _is_junk_required_term,
    anchor_required_terms,
    build_case_exam_figure_corpus,
    build_case_official_answer_corpus,
    build_human_escalation_queues,
    build_no_human_labels_for_case,
    build_textbook_anchor_corpus,
    merge_independent_resolution_labels,
    squeeze_required_terms,
    summarize_no_human_fixture,
)
from scripts.poc_luban_case_grading_three_arms import extract_required_terms  # noqa: E402


DEFAULT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/luban_no_human_v1_5/20260601_textbook_anchored"
DEFAULT_PRIOR_REPORT = (
    PROJECT_ROOT
    / "artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_185157.json"
)
DEFAULT_AGENT_A_LABELS: Path | None = None
DEFAULT_AGENT_B_LABELS: Path | None = None
R4_POINT_CLASSIFICATION = (
    PROJECT_ROOT
    / "artifacts/luban_no_human_v1_5/content_markdown_reanchor_pilot_gate_20260602/point_classification_pilot_gate_20260602.json"
)
R5_POINT_CLASSIFICATION = (
    PROJECT_ROOT
    / "artifacts/luban_no_human_v1_5/per_term_anchor_r5_20260602/point_classification_r5_20260602.json"
)
SHORT_COMMON_ANCHOR_TERMS = {
    "浇筑",
    "限制",
    "防护",
    "环境",
    "勘察",
    "施工",
    "管理",
    "质量",
    "安全",
    "审核",
    "审批",
    "验收",
    "资料",
    "场地",
    "设备",
    "费用",
    "计划",
    "组织",
}
R6_RUBRIC_TO_TEXTBOOK_TERMS: dict[tuple[str, str], list[str]] = {
    ("Q3-1A433000", "P4"): ["材料合格", "符合标准"],
    ("Q3-1A433000", "P5"): ["含泥量"],
    ("Q3-1A433000", "P6"): ["防水砂浆"],
    ("Q3-1A433000", "P8"): ["养护时间"],
    ("Q3-1A433000", "P9"): ["室内环境污染物浓度检测"],
    ("Q5-1A432000", "P5"): ["施工场地", "图纸会审", "设计图纸交底", "交叉配合"],
    ("Q6-1A413000-罚则", "P1"): ["搭接长度", "分格缝", "温度变化"],
    ("Q10-1A422000", "P1"): ["水泥砂浆粘贴", "饰面砖"],
    ("Q10-1A422000", "P3"): ["脚手架"],
    ("Q13-1A421000", "P2"): ["技术负责人"],
    ("Q16-1A436000", "P2"): ["保护层厚度", "混凝土垫层"],
    ("Q16-1A436000", "P4"): ["八字形"],
    ("Q18-1A434000", "P3"): ["组织管理层"],
}
R6_CALCULATION_TERMS: dict[tuple[str, str], list[str]] = {
    ("Q3-1A433000", "P2"): ["主体结构2天"],
    ("Q3-1A433000", "P3"): ["室内装修3天"],
}
_ANCHOR_DROP_CHARS = set(" \t\r\n()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’/／-—_[]【】")
_ANCHOR_CONNECTOR_CHARS = set("和及与")
_ANCHOR_ENUM_CHARS = set("①②③④⑤⑥⑦⑧⑨⑩")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stable_unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        clean = _clean_required_term(term)
        compact = re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’]+", "", clean)
        if not compact or compact in seen or _is_junk_required_term(clean):
            continue
        seen.add(compact)
        result.append(clean)
    return result


def _chinese_char_count(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", str(value or "")))


def _is_distinctive_textbook_term(term: str) -> bool:
    clean = _clean_required_term(term)
    if _is_junk_required_term(clean) or _is_short_common_single_term(clean):
        return False
    if _chinese_char_count(clean) < 3:
        return False
    if re.fullmatch(r"(?:应|不妥|太小|不当|不得|至少|及以上|不少于|不应小于|≤|≥|\d+[%米人天d]+)+", clean, flags=re.I):
        return False
    return True


def _r6_target_terms(case_id: str, point_id: str) -> list[str]:
    return [
        term
        for term in R6_RUBRIC_TO_TEXTBOOK_TERMS.get((case_id, point_id), [])
        if _is_distinctive_textbook_term(term)
    ]


def _r6_calculation_terms(case_id: str, point_id: str) -> list[str]:
    return list(R6_CALCULATION_TERMS.get((case_id, point_id), []))


def _anchor_normalized_with_offsets(value: Any) -> tuple[str, list[int]]:
    """Normalize only for source anchoring; this is not synonym expansion."""

    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"^[\s①②③④⑤⑥⑦⑧⑨⑩]*(?:\(?\d+[）).、]\s*)+", "", text)
    chars: list[str] = []
    offsets: list[int] = []
    index = 0
    while index < len(text):
        char = text[index]
        if text.startswith("以及", index):
            index += 2
            continue
        if char in _ANCHOR_ENUM_CHARS or char in _ANCHOR_DROP_CHARS or char.isspace():
            index += 1
            continue
        if char in _ANCHOR_CONNECTOR_CHARS:
            index += 1
            continue
        chars.append(char)
        offsets.append(index)
        index += 1
    return "".join(chars), offsets


def _anchor_normalized(value: Any) -> str:
    return _anchor_normalized_with_offsets(value)[0]


def _normalized_text_contains(text: Any, term: Any) -> bool:
    normalized_term = _anchor_normalized(term)
    if not normalized_term:
        return False
    return normalized_term in _anchor_normalized(text)


def _normalized_anchor_for_record(term: str, record: dict[str, Any]) -> dict[str, Any] | None:
    normalized_term = _anchor_normalized(term)
    if not normalized_term:
        return None
    text = str(record.get("text") or "")
    normalized_text, offsets = _anchor_normalized_with_offsets(text)
    start = normalized_text.find(normalized_term)
    if start < 0 or start >= len(offsets):
        return None
    end = start + len(normalized_term) - 1
    if end >= len(offsets):
        return None
    raw_start = offsets[start]
    raw_end = offsets[end] + 1
    return {
        "source_path": record.get("source_path") or "",
        "source_class": record.get("source_class") or "",
        "json_pointer": record.get("json_pointer") or "",
        "chunk_id": record.get("chunk_id") or "",
        "node_code": record.get("node_code") or "",
        "page_num": record.get("page_num"),
        "start": raw_start,
        "end": raw_end,
        "span_text": text[raw_start:raw_end],
        "match_method": "anchor_strong_normalized",
        "content_hash": record.get("content_hash") or "",
    }


def _strong_textbook_anchor_for_term(term: str, corpus: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in corpus:
        if str(record.get("source_class") or "") != "textbook":
            continue
        anchor = _normalized_anchor_for_record(term, record)
        if anchor and _valid_textbook_anchor(anchor, corpus):
            return anchor
    return None


def _split_outside_brackets(text: str, separators: set[str]) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in str(text or ""):
        if char in {"(", "（"}:
            depth += 1
        elif char in {")", "）"} and depth > 0:
            depth -= 1
        if char in separators and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _split_list_tail(value: str) -> list[str]:
    text = str(value or "")
    text = re.split(r"(?:近义不算|同义不算|不得分|按写对|每项|满分)", text, 1)[0]
    text = re.sub(r"[（(][^()（）]*(?:项列举|列举|口径|任选)[^()（）]*[)）]", "", text)
    pieces: list[str] = []
    enumerated = re.findall(r"(?:[①②③④⑤⑥⑦⑧⑨⑩]|\(?\d+[）).、])\s*([^;；。]+)", text)
    if enumerated:
        pieces.extend(enumerated)
    else:
        pieces.extend(_split_outside_brackets(text, {"、", ",", "，", "/", "／", ";", "；"}))
    return _stable_unique_terms([piece for piece in pieces if 1 < len(str(piece).strip()) <= 40])


def _explicit_list_terms(point: dict[str, Any], corpus: list[dict[str, Any]]) -> list[str]:
    """Prefer the official list numerator/denominator over repaired free-text anchors."""

    texts = [
        str(point.get("label") or ""),
        str(point.get("list_rule") or ""),
        str(point.get("official_basis") or ""),
    ]
    candidates: list[str] = []
    for text in texts:
        for pattern in (
            r"(?:规范术语原文|标准术语原文|规范术语|标准术语|必须写出规范术语)[:：]\s*([^。；;]+)",
            r"应得分项为\d+项[:：]\s*([^。；;]+)",
            r"——\s*([^。；;]+)",
        ):
            for match in re.finditer(pattern, text):
                candidates.extend(_split_list_tail(match.group(1)))
        for match in re.finditer(r"[（(]([^()（）]{2,120})[)）]", text):
            inner = match.group(1)
            if re.search(r"项列举|近义|同义|不得分|每项|满分", inner):
                continue
            terms = _split_list_tail(inner)
            if len(terms) >= 2:
                candidates.extend(terms)
    anchored_terms: list[str] = []
    for term in _stable_unique_terms(candidates):
        anchored = anchor_required_terms([term], corpus).get("terms") or []
        if anchored and anchored[0].get("anchors"):
            anchored_terms.append(term)
    return _stable_unique_terms(anchored_terms)


def _is_short_common_single_term(term: str) -> bool:
    clean = _clean_required_term(term)
    return len(clean) <= 3 and clean in SHORT_COMMON_ANCHOR_TERMS


def _valid_textbook_anchor(anchor: dict[str, Any], corpus: list[dict[str, Any]]) -> bool:
    if str(anchor.get("source_class") or "") != "textbook":
        return False
    chunk_id = str(anchor.get("chunk_id") or "")
    quote = str(anchor.get("span_text") or "")
    if not chunk_id or not quote:
        return False
    for record in corpus:
        if str(record.get("source_class") or "") != "textbook":
            continue
        if str(record.get("chunk_id") or "") != chunk_id:
            continue
        if str(anchor.get("content_hash") or "") and str(record.get("content_hash") or "") != str(anchor.get("content_hash") or ""):
            continue
        if _normalized_text_contains(record.get("text") or "", quote):
            return True
    return False


def _source_summary(provenance: dict[str, Any], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    term_rows = list(provenance.get("terms") or [])
    selected_textbook_anchors: list[dict[str, Any]] = []
    term_anchor_map: dict[str, dict[str, Any]] = {}
    selected_official_anchors: list[dict[str, Any]] = []
    selected_exam_figure_anchors: list[dict[str, Any]] = []
    for term_row in term_rows:
        term = str(term_row.get("term") or "").strip()
        anchors = list(term_row.get("anchors") or [])
        valid_textbook = [anchor for anchor in anchors if _valid_textbook_anchor(anchor, corpus)]
        if not valid_textbook and term:
            strong_anchor = _strong_textbook_anchor_for_term(term, corpus)
            if strong_anchor:
                valid_textbook = [strong_anchor]
        if valid_textbook:
            first = valid_textbook[0]
            selected_textbook_anchors.append(first)
            term_anchor_map[term] = {
                "anchor_source": "textbook",
                "chunk_id": str(first.get("chunk_id") or ""),
                "node_code": str(first.get("node_code") or ""),
                "page_num": first.get("page_num"),
                "textbook_quote": str(first.get("span_text") or ""),
                "start": first.get("start"),
                "end": first.get("end"),
                "verified": True,
                "match_method": str(first.get("match_method") or ""),
            }
            continue
        official = next((anchor for anchor in anchors if str(anchor.get("source_class") or "") == "official_answer"), None)
        if official:
            selected_official_anchors.append(official)
            term_anchor_map[term] = {
                "anchor_source": "official_answer_weak",
                "chunk_id": "",
                "textbook_quote": str(official.get("span_text") or ""),
                "verified": False,
                "match_method": str(official.get("match_method") or ""),
            }
            continue
        exam_figure = next((anchor for anchor in anchors if str(anchor.get("source_class") or "") == "exam_figure"), None)
        if exam_figure:
            selected_exam_figure_anchors.append(exam_figure)
            term_anchor_map[term] = {
                "anchor_source": "exam_figure",
                "chunk_id": "",
                "textbook_quote": str(exam_figure.get("span_text") or ""),
                "verified": False,
                "match_method": str(exam_figure.get("match_method") or ""),
            }
            continue
        term_anchor_map[term] = {
            "anchor_source": "non_textbook",
            "chunk_id": "",
            "textbook_quote": "",
            "verified": False,
            "match_method": "",
        }
    if selected_textbook_anchors:
        first = selected_textbook_anchors[0]
        return {
            "anchor_source": "textbook",
            "chunk_id": str(first.get("chunk_id") or ""),
            "textbook_quote": str(first.get("span_text") or ""),
            "term_anchor_map": term_anchor_map,
        }
    if selected_official_anchors:
        first = selected_official_anchors[0]
        return {
            "anchor_source": "official_answer_weak",
            "chunk_id": "",
            "textbook_quote": str(first.get("span_text") or ""),
            "term_anchor_map": term_anchor_map,
        }
    if selected_exam_figure_anchors:
        first = selected_exam_figure_anchors[0]
        return {
            "anchor_source": "exam_figure",
            "chunk_id": "",
            "textbook_quote": str(first.get("span_text") or ""),
            "term_anchor_map": term_anchor_map,
        }
    return {"anchor_source": "non_textbook", "chunk_id": "", "textbook_quote": "", "term_anchor_map": term_anchor_map}


def _textbook_verified_terms(terms: list[str], source: dict[str, Any]) -> list[str]:
    term_anchor_map = source.get("term_anchor_map") if isinstance(source.get("term_anchor_map"), dict) else {}
    return [
        term
        for term in terms
        if (term_anchor_map.get(term) or {}).get("anchor_source") == "textbook"
        and (term_anchor_map.get(term) or {}).get("verified") is True
    ]


def _distinctive_phrase_for_short_term(term: str, point_text: str, corpus: list[dict[str, Any]]) -> str:
    clean = _clean_required_term(term)
    candidates: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fffA-Za-z0-9]{4,16}", str(point_text or "")):
        candidate = _clean_required_term(match.group(0))
        if clean in candidate and len(candidate) > 3:
            candidates.append(candidate)
    if clean == "防护" and "防护栏杆" in str(point_text or ""):
        candidates.insert(0, "防护栏杆")
    if clean == "浇筑" and "浇筑顺序" in str(point_text or ""):
        candidates.insert(0, "浇筑顺序")
    ranked = sorted(
        _stable_unique_terms(candidates),
        key=lambda value: (len(value), value),
    )
    for candidate in ranked:
        provenance = anchor_required_terms([candidate], corpus)
        if _source_summary(provenance, corpus)["anchor_source"] == "textbook":
            return candidate
    return ""


def _repair_short_common_single_terms(
    terms: list[str],
    *,
    point_text: str,
    corpus: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    if len(terms) != 1 or not _is_short_common_single_term(terms[0]):
        return terms, {}
    replacement = _distinctive_phrase_for_short_term(terms[0], point_text, corpus)
    if replacement:
        return [replacement], {
            "short_common_anchor_repair": {
                "original_term": terms[0],
                "replacement_term": replacement,
            }
        }
    return [], {
        "short_common_anchor_repair": {
            "original_term": terms[0],
            "replacement_term": "",
            "status": "unresolved",
        }
    }


def _point_text(point: dict[str, Any]) -> str:
    return "\n".join(str(point.get(field) or "") for field in ("label", "official_basis", "list_rule"))


def _is_figure_point(point: dict[str, Any]) -> bool:
    text = _point_text(point)
    return bool(re.search(r"(?:图中[①②③④⑤⑥⑦⑧⑨⑩]|\b图\d*机具名称|编号设施名称定位|机具使用先后顺序)", text))


def _is_cross_subject_point(point: dict[str, Any]) -> bool:
    text = _point_text(point)
    return bool(re.search(r"虚工作|虚箭线|虚活动|虚工序|关键线路", text))


def _calculation_expected_terms(point: dict[str, Any]) -> list[str]:
    text = _point_text(point)
    if not re.search(r"=|＝|计算|总工期|用量|价款|费用|劳动力", text):
        return []
    terms: list[str] = []
    for match in re.finditer(r"(?:=|＝)\s*(\d+(?:\.\d+)?\s*(?:kg|万元|天|人|名|个月|%))", text, flags=re.I):
        terms.append(re.sub(r"\s+", "", match.group(1)))
    for match in re.finditer(r"(?:总工期为?|取整)\s*(\d+(?:\.\d+)?\s*(?:kg|万元|天|人|名|个月|%))", text, flags=re.I):
        terms.append(re.sub(r"\s+", "", match.group(1)))
    if not terms:
        for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(kg|万元|天|人|名|个月)", text, flags=re.I):
            terms.append(f"{value}{unit}")
    if "取整" in text:
        rounded = re.findall(r"取整\s*(\d+(?:\.\d+)?)\s*(人|名|kg|万元|天|个月)", text, flags=re.I)
        terms.extend(f"{value}{unit}" for value, unit in rounded)
    selected = terms[-2:] if len(terms) > 2 else terms
    unique: list[str] = []
    seen: set[str] = set()
    for term in selected:
        clean = str(term or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def _figure_terms(point: dict[str, Any]) -> list[str]:
    text = _point_text(point)
    if "定位" in text and ("：" in text or ":" in text):
        text = re.split(r"[:：]", text, 1)[1]
    sequence = re.search(r"\b[A-Z](?:-[A-Z]){2,}\b", text)
    if sequence:
        return [sequence.group(0)]
    terms = re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]\s*([^/；;，,。()（）]+)", text)
    if not terms:
        terms = re.findall(r"[A-Z]\s*([^\s/；;，,。()（）]+)", text)
    cleaned = []
    for term in terms:
        term = re.split(r"\\n|\n|列举型|须含|图中", str(term), 1)[0]
        if term:
            cleaned.append(term)
    return _stable_unique_terms(cleaned)


def _point_type(point: dict[str, Any]) -> str:
    if _is_figure_point(point):
        return "figure_label"
    if _calculation_expected_terms(point):
        return "calculation"
    if _is_cross_subject_point(point):
        return "non_textbook"
    return "text_term"


# r7 provenance adjudication (Claude + Codex consensus, 2026-06-02).
# Cross-node textbook anchors where the term matches verbatim but the cited chunk is a
# different institutional context (张冠李戴) → force official_answer_weak.
# `reanchor` moves a term to the chunk that is its true authoritative passage.
# Keyed by (case_id, point_id, term).
_ENERGY_CARBON_CHUNK = "1A422000_055_0081"
# `from_node`: downgrade fires only when the term is anchored to that mis-provenance node;
# if the same term legitimately anchors elsewhere (its true 防水/能源 passage), it survives.
PROVENANCE_ADJUDICATION: dict[tuple[str, str, str], dict[str, str]] = {
    ("Q3-1A433000", "P1", "资金"): {"decision": "downgrade", "from_node": "1A421000"},
    ("Q3-1A433000", "P4", "材料合格"): {"decision": "downgrade", "from_node": "1A413030"},
    ("Q3-1A433000", "P4", "符合标准"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q3-1A433000", "P7", "宜分层"): {"decision": "downgrade", "from_node": "1A411011"},
    ("Q4-1A434000-罚则", "P3", "标识"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q6-1A413000-罚则", "P1", "温度变化"): {"decision": "downgrade", "from_node": "1A438000"},
    ("Q7-1A431000", "P1", "塔吊"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q7-1A431000", "P1", "施工电梯"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q7-1A431000", "P2", "防火"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q7-1A431000", "P3", "广播"): {"decision": "downgrade", "from_node": "1A421000"},
    ("Q11-1A434020", "P3", "盥洗室"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q11-1A434020", "P3", "厕所"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q14-1A430000", "P1", "布料机"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q17-1A433000", "P5", "材料合格"): {"decision": "downgrade", "from_node": "1A413030"},
    ("Q17-1A433000", "P5", "压实"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q3-1A433000", "P6", "防水砂浆"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q13-1A421000", "P2", "技术负责人"): {"decision": "downgrade", "from_node": "1A437000"},
    ("Q18-1A434000", "P6", "变形缝"): {"decision": "downgrade", "from_node": "1A422000"},
    ("Q14-1A430000", "P5", "汽油"): {"decision": "reanchor", "chunk_id": _ENERGY_CARBON_CHUNK},
    ("Q14-1A430000", "P5", "燃气"): {"decision": "reanchor", "chunk_id": _ENERGY_CARBON_CHUNK},
}


def _provenance_confidence(node_code: str, case_node: str) -> str:
    node = str(node_code or "")
    case = str(case_node or "")
    if not case or case == "NA" or not node:
        return "high"
    if node.startswith(case) or node[:5] == case[:5]:
        return "high"
    return "needs_review"


def _apply_provenance_adjudication(
    source: dict[str, Any],
    *,
    case_id: str,
    point_id: str,
    case_node: str,
    corpus: list[dict[str, Any]],
    adjudication: dict[tuple[str, str, str], dict[str, str]] = PROVENANCE_ADJUDICATION,
) -> dict[str, Any]:
    """Apply the reviewed cross-node provenance verdicts; never mutates inputs.

    Downgrade kills mis-provenanced (张冠李戴) textbook terms to weak. Reanchor moves a term
    to its authoritative chunk only if it verbatim-verifies there (otherwise it downgrades —
    no faked anchors). Unadjudicated cross-node textbook terms are flagged needs_review so
    future rebuilds surface them instead of silently certifying.
    """
    term_anchor_map = source.get("term_anchor_map")
    if not isinstance(term_anchor_map, dict) or not term_anchor_map:
        return source
    updated: dict[str, Any] = {}
    for term, entry in term_anchor_map.items():
        if not isinstance(entry, dict):
            updated[term] = entry
            continue
        rule = adjudication.get((str(case_id), str(point_id), str(term)))
        if rule and rule.get("decision") == "downgrade":
            from_node = str(rule.get("from_node") or "")
            current_node = str(entry.get("node_code") or "")
            # Only kill the mis-provenanced anchor; a legitimate anchor to a different
            # (authoritative) chunk for the same term survives.
            if not from_node or current_node.startswith(from_node):
                updated[term] = {
                    **entry,
                    "anchor_source": "official_answer_weak",
                    "chunk_id": "",
                    "verified": False,
                    "provenance_confidence": "downgraded_mis_provenance",
                }
                continue
        if rule and rule.get("decision") == "reanchor":
            target = str(rule.get("chunk_id") or "")
            record = next(
                (
                    record
                    for record in corpus
                    if str(record.get("chunk_id") or "") == target and str(record.get("source_class") or "") == "textbook"
                ),
                None,
            )
            if record and _normalized_text_contains(record.get("text"), term):
                anchor = _normalized_anchor_for_record(term, record)
                updated[term] = {
                    **entry,
                    "anchor_source": "textbook",
                    "chunk_id": target,
                    "node_code": str(record.get("node_code") or ""),
                    "textbook_quote": str((anchor or {}).get("span_text") or term),
                    "verified": True,
                    "match_method": "reanchored_authoritative",
                    "provenance_confidence": "high",
                }
            else:
                updated[term] = {
                    **entry,
                    "anchor_source": "official_answer_weak",
                    "chunk_id": "",
                    "verified": False,
                    "provenance_confidence": "downgraded_mis_provenance",
                }
            continue
        if entry.get("anchor_source") == "textbook":
            updated[term] = {
                **entry,
                "provenance_confidence": entry.get("provenance_confidence")
                or _provenance_confidence(str(entry.get("node_code") or ""), case_node),
            }
            continue
        updated[term] = entry
    textbook_first = next(
        (
            entry
            for entry in updated.values()
            if isinstance(entry, dict) and entry.get("anchor_source") == "textbook" and entry.get("verified")
        ),
        None,
    )
    if textbook_first:
        return {
            **source,
            "anchor_source": "textbook",
            "chunk_id": str(textbook_first.get("chunk_id") or ""),
            "textbook_quote": str(textbook_first.get("textbook_quote") or ""),
            "term_anchor_map": updated,
        }
    if source.get("anchor_source") == "textbook":
        official_first = next(
            (entry for entry in updated.values() if isinstance(entry, dict) and entry.get("anchor_source") == "official_answer_weak"),
            None,
        )
        return {
            **source,
            "anchor_source": "official_answer_weak",
            "chunk_id": "",
            "textbook_quote": str((official_first or {}).get("textbook_quote") or ""),
            "term_anchor_map": updated,
        }
    return {**source, "term_anchor_map": updated}


def _required_terms_by_point(
    case: dict[str, Any],
    corpus: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, int]]:
    terms_by_point: dict[str, list[str]] = {}
    squeeze_by_point: dict[str, dict[str, Any]] = {}
    metadata_by_point: dict[str, dict[str, Any]] = {}
    root_counts: dict[str, int] = {}
    textbook_corpus = [record for record in corpus if str(record.get("source_class") or "") == "textbook"]
    case_id = str(case.get("case_id") or "")
    for point in case.get("gold_scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        r6_calculation_terms = _r6_calculation_terms(case_id, point_id)
        point_type = "calculation" if r6_calculation_terms else _point_type(point)
        calculation_terms = r6_calculation_terms or (_calculation_expected_terms(point) if point_type == "calculation" else [])
        if point_type == "calculation":
            raw_terms = []
            squeezed = {
                "terms": [],
                "repairs": [],
                "root_cause_counts": {},
                "calculation_expected_terms": calculation_terms,
                "term_path": "calculation_recompute",
            }
        elif point_type == "figure_label":
            raw_terms = _figure_terms(point)
            squeezed = {
                **squeeze_required_terms(raw_terms, corpus),
                "terms": _figure_terms(point),
                "term_path": "exam_figure_label",
            }
        elif point_type == "non_textbook":
            raw_terms = extract_required_terms(point)
            squeezed = {
                "terms": [],
                "repairs": [{"category": "non_textbook_cross_subject", "original_term": term} for term in raw_terms],
                "root_cause_counts": {"non_textbook_cross_subject": len(raw_terms)},
                "term_path": "non_textbook_defer_to_po",
            }
        else:
            raw_terms = extract_required_terms(point)
            squeezed = squeeze_required_terms(raw_terms, corpus)
            explicit_terms = _explicit_list_terms(point, corpus)
            if explicit_terms:
                squeezed = {
                    **squeezed,
                    "terms": explicit_terms,
                    "list_rule_denominator_source": "explicit_official_list_terms",
                }
            r6_terms = _r6_target_terms(case_id, point_id)
            if r6_terms:
                squeezed = {
                    **squeezed,
                    "terms": r6_terms,
                    "rubric_to_textbook_terms_r6": True,
                    "r6_original_terms": list(squeezed.get("terms") or []),
                }
        if point_type == "text_term" and not squeezed["terms"]:
            fallback_text = "\n".join(
                str(point.get(field) or "") for field in ("label", "official_basis", "list_rule")
            )
            fallback_terms = _anchored_subterms(fallback_text, corpus)
            if fallback_terms:
                squeezed = {
                    **squeezed,
                    "terms": fallback_terms,
                    "fallback_repair": "label_subterms_anchored_to_official_sources",
                }
                root_counts["label_subterms_anchored_to_official_sources"] = (
                    root_counts.get("label_subterms_anchored_to_official_sources", 0) + 1
                )
        display_terms = list(squeezed["terms"])
        if point_type == "text_term":
            display_terms, short_repair = _repair_short_common_single_terms(
                display_terms,
                point_text=_point_text(point),
                corpus=textbook_corpus,
            )
            if short_repair:
                squeezed = {**squeezed, **short_repair, "terms": display_terms}
                if not display_terms:
                    root_counts["short_common_anchor_unresolved"] = root_counts.get("short_common_anchor_unresolved", 0) + 1
        provenance = anchor_required_terms(display_terms, corpus)
        source = _source_summary(provenance, corpus)
        if point_type == "text_term" and source["anchor_source"] == "exam_figure":
            source = {
                "anchor_source": "official_answer_weak",
                "chunk_id": "",
                "textbook_quote": source.get("textbook_quote") or "",
                "term_anchor_map": source.get("term_anchor_map") or {},
            }
        if point_type == "text_term" and display_terms and source["anchor_source"] == "official_answer_weak":
            repaired_terms = _anchored_subterms(" ".join(display_terms), textbook_corpus)
            if repaired_terms and (len(display_terms) == 1 or len(repaired_terms) >= len(display_terms)):
                display_terms = repaired_terms
                display_terms, short_repair = _repair_short_common_single_terms(
                    display_terms,
                    point_text=_point_text(point),
                    corpus=textbook_corpus,
                )
                provenance = anchor_required_terms(display_terms, textbook_corpus)
                source = _source_summary(provenance, textbook_corpus)
                squeezed = {
                    **squeezed,
                    **short_repair,
                    "terms": display_terms,
                    "official_answer_weak_repaired_to_content_markdown": True,
                }
                root_counts["official_answer_weak_repaired_to_content_markdown"] = (
                    root_counts.get("official_answer_weak_repaired_to_content_markdown", 0) + 1
                )
        if point_type == "calculation":
            source = {"anchor_source": "calculation", "chunk_id": "", "textbook_quote": "", "term_anchor_map": {}}
        elif point_type == "figure_label":
            source = {
                "anchor_source": "exam_figure",
                "chunk_id": "",
                "textbook_quote": source.get("textbook_quote") or "",
                "term_anchor_map": source.get("term_anchor_map") or {},
            }
        elif point_type == "non_textbook":
            source = {"anchor_source": "non_textbook", "chunk_id": "", "textbook_quote": "", "term_anchor_map": {}}
        source = _apply_provenance_adjudication(
            source,
            case_id=case_id,
            point_id=point_id,
            case_node=_case_node_code(case),
            corpus=corpus,
        )
        label_terms = display_terms
        if point_type == "text_term" and source["anchor_source"] == "textbook":
            label_terms = _textbook_verified_terms(display_terms, source)
            if label_terms != display_terms:
                squeezed = {
                    **squeezed,
                    "weak_anchor_terms": [term for term in display_terms if term not in label_terms],
                    "list_rule_denominator_source": "textbook_verified_term_subset",
                }
        elif point_type == "text_term" and display_terms and source["anchor_source"] != "textbook":
            label_terms = []
            squeezed = {
                **squeezed,
                "weak_anchor_terms": display_terms,
                "weak_anchor_source": source["anchor_source"],
            }
        terms_by_point[point_id] = label_terms
        squeeze_by_point[point_id] = {"raw_terms": raw_terms, **squeezed}
        metadata_by_point[point_id] = {
            "point_type": point_type,
            "calculation_expected_terms_v1_5": calculation_terms,
            "display_terms": display_terms,
            "label_terms": label_terms,
            "provenance": provenance,
            **source,
        }
        for category, count in (squeezed.get("root_cause_counts") or {}).items():
            root_counts[str(category)] = root_counts.get(str(category), 0) + int(count)
    return terms_by_point, squeeze_by_point, metadata_by_point, dict(sorted(root_counts.items()))


def _ledger_score_map(sample: dict[str, Any], points_by_id: dict[str, dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    ledger = sample.get("ground_truth_ledger") if isinstance(sample.get("ground_truth_ledger"), dict) else {}
    for row in ledger.get("point_hits") or []:
        point_id = str(row.get("point_id") or "")
        status = str(row.get("hit") or "")
        max_score = float((points_by_id.get(point_id) or {}).get("max_score") or 0)
        result[point_id] = max_score if status == "hit" else (max_score / 2 if status == "partial" else 0.0)
    return result


def _point_score_from_result(row: dict[str, Any], point_ids: set[str]) -> dict[str, float]:
    scores = {point_id: 0.0 for point_id in point_ids}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    for item in result.get("rubric_items") or []:
        criterion = str(item.get("criterion") or "")
        if "::" in criterion:
            point_id = criterion.split("::", 1)[0]
            if point_id in scores:
                scores[point_id] += float(item.get("awarded_score") or 0)
    return {key: round(value, 4) for key, value in scores.items()}


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _case_node_code(case: dict[str, Any]) -> str:
    return str(case.get("question_node") or case.get("node_code") or "").strip()


def _case_scoped_corpus(corpus: list[dict[str, Any]], case: dict[str, Any]) -> list[dict[str, Any]]:
    node = _case_node_code(case)
    if not node or node == "NA":
        return corpus
    same_node = [record for record in corpus if str(record.get("node_code") or "").startswith(node)]
    same_parent = [record for record in corpus if str(record.get("node_code") or "")[:5] == node[:5] and record not in same_node]
    others = [record for record in corpus if record not in same_node and record not in same_parent]
    return [*same_node, *same_parent, *others]


def _anchor_match_scope(case: dict[str, Any], node_code: str) -> str:
    case_node = _case_node_code(case)
    node = str(node_code or "")
    if not case_node or case_node == "NA" or not node:
        return "all_kb"
    if node.startswith(case_node):
        return "case_node"
    if node[:5] == case_node[:5]:
        return "case_parent_sibling"
    return "all_kb_fallback"


def _point_count_summary(fixture: dict[str, Any]) -> dict[str, Any]:
    points = [point for case in fixture.get("cases") or [] for point in case.get("gold_scoring_points") or []]
    point_type_counts: dict[str, int] = {}
    anchor_source_counts: dict[str, int] = {}
    for point in points:
        point_type = str(point.get("point_type") or "unknown")
        anchor_source = str(point.get("anchor_source") or "unknown")
        point_type_counts[point_type] = point_type_counts.get(point_type, 0) + 1
        anchor_source_counts[anchor_source] = anchor_source_counts.get(anchor_source, 0) + 1
    textbook_count = anchor_source_counts.get("textbook", 0)
    return {
        "point_count": len(points),
        "point_type_counts": dict(sorted(point_type_counts.items())),
        "anchor_source_counts": dict(sorted(anchor_source_counts.items())),
        "textbook_anchor_point_ratio": round(textbook_count / len(points), 4) if points else 0.0,
    }


def _compare_prior_report(prior_report_path: Path | None, fixture: dict[str, Any]) -> dict[str, Any]:
    if not prior_report_path or not prior_report_path.exists():
        return {"available": False, "reason": "missing_prior_report"}
    prior = _read_json(prior_report_path)
    labels: dict[tuple[str, str, str], float] = {}
    deterministic_points_by_sample: dict[tuple[str, str], set[str]] = {}
    ledger_scores: dict[tuple[str, str, str], float] = {}
    for case in fixture.get("cases") or []:
        points_by_id = {str(point.get("point_id") or ""): point for point in case.get("gold_scoring_points") or []}
        for sample in case.get("eval_samples") or []:
            key = (str(case.get("case_id")), str(sample.get("student_id")))
            deterministic_points_by_sample[key] = set()
            for label in sample.get("no_human_v1_5_labels") or []:
                if not label.get("is_deterministic"):
                    continue
                point_id = str(label.get("point_id"))
                deterministic_points_by_sample[key].add(point_id)
                labels[(key[0], key[1], point_id)] = float(label.get("score") or 0)
            for point_id, score in _ledger_score_map(sample, points_by_id).items():
                ledger_scores[(key[0], key[1], point_id)] = score
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in prior.get("rows") or []:
        arm = str(row.get("arm") or "")
        case_id = str(row.get("case_id") or "")
        sample_id = str(row.get("sample_id") or "")
        point_ids = deterministic_points_by_sample.get((case_id, sample_id), set())
        if not point_ids:
            continue
        pred_scores = _point_score_from_result(row, point_ids)
        gold_total = sum(labels.get((case_id, sample_id, point_id), 0.0) for point_id in point_ids)
        v0_total = sum(ledger_scores.get((case_id, sample_id, point_id), 0.0) for point_id in point_ids)
        pred_total = sum(pred_scores.values())
        grouped.setdefault(arm, []).append(
            {
                "case_id": case_id,
                "sample_id": sample_id,
                "deterministic_points": sorted(point_ids),
                "v1_5_gold_score": round(gold_total, 4),
                "v0_ledger_score": round(v0_total, 4),
                "pred_score_on_deterministic_subset": round(pred_total, 4),
                "abs_delta_v1_5": round(abs(pred_total - gold_total), 4),
                "abs_delta_v0": round(abs(pred_total - v0_total), 4),
            }
        )
    return {
        "available": True,
        "prior_report_path": str(prior_report_path),
        "summary": {
            arm: {
                "sample_count": len(rows),
                "mean_abs_score_delta_v1_5": _avg([float(row["abs_delta_v1_5"]) for row in rows]),
                "mean_abs_score_delta_v0_same_subset": _avg([float(row["abs_delta_v0"]) for row in rows]),
            }
            for arm, rows in sorted(grouped.items())
        },
        "rows": grouped,
    }


def _artifact_stage(output_dir: Path) -> str:
    return "r6" if "rubric_to_textbook_r6" in str(output_dir) else "r5"


def _previous_point_map(stage: str) -> dict[tuple[str, str], dict[str, Any]]:
    previous_path = R5_POINT_CLASSIFICATION if stage == "r6" else R4_POINT_CLASSIFICATION
    if not previous_path.exists():
        return {}
    rows = _read_json(previous_path)
    if not isinstance(rows, list):
        return {}
    return {
        (str(row.get("case_id") or ""), str(row.get("point_id") or "")): row
        for row in rows
        if isinstance(row, dict)
    }


def _point_row(
    *,
    case: dict[str, Any],
    point: dict[str, Any],
    sample: dict[str, Any] | None,
    label: dict[str, Any] | None,
    corpus: list[dict[str, Any]],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    anchor = {
        "source_class": point.get("anchor_source"),
        "chunk_id": point.get("chunk_id"),
        "span_text": point.get("textbook_quote"),
        "content_hash": "",
    }
    verified = False
    if point.get("anchor_source") == "textbook":
        for record in corpus:
            if str(record.get("chunk_id") or "") == str(point.get("chunk_id") or ""):
                anchor["content_hash"] = str(record.get("content_hash") or "")
                break
        verified = _valid_textbook_anchor(anchor, corpus)
    previous = previous or {}
    term_anchor_map = point.get("term_anchor_map") if isinstance(point.get("term_anchor_map"), dict) else {}
    audited_term_anchor_map: dict[str, Any] = {}
    for term, data in term_anchor_map.items():
        if not isinstance(data, dict):
            audited_term_anchor_map[str(term)] = data
            continue
        audited_term_anchor_map[str(term)] = {
            **data,
            "match_scope": _anchor_match_scope(case, str(data.get("node_code") or "")),
        }
    return {
        "case_id": case.get("case_id"),
        "point_id": point.get("point_id"),
        "point_type": point.get("point_type"),
        "anchor_source": point.get("anchor_source"),
        "chunk_id": point.get("chunk_id"),
        "textbook_quote": point.get("textbook_quote"),
        "verified_in_content_markdown": verified,
        "required_terms": point.get("required_terms_v1_5") or [],
        "display_terms": point.get("display_terms_v1_5") or point.get("required_terms_v1_5") or [],
        "term_anchor_map": audited_term_anchor_map,
        "calculation_expected_terms": point.get("calculation_expected_terms_v1_5") or [],
        "previous_anchor_source": previous.get("anchor_source") or "",
        "previous_chunk_id": previous.get("chunk_id") or "",
        "previous_textbook_quote": previous.get("textbook_quote") or "",
        "rescued_from_r4": bool(previous.get("anchor_source") not in {"", "textbook"} and point.get("anchor_source") == "textbook"),
        "rescued_from_r5": bool(previous.get("anchor_source") not in {"", "textbook"} and point.get("anchor_source") == "textbook"),
        "label": point.get("label"),
        "sample_student_id": (sample or {}).get("student_id"),
        "sample_answer": (sample or {}).get("answer_text"),
        "sample_hit": (label or {}).get("hit"),
        "sample_score": (label or {}).get("score"),
        "sample_resolution_class": (label or {}).get("resolution_class"),
    }


def _point_classification_rows(fixture: dict[str, Any], corpus: list[dict[str, Any]], *, stage: str) -> list[dict[str, Any]]:
    previous = _previous_point_map(stage)
    rows: list[dict[str, Any]] = []
    for case in fixture.get("cases") or []:
        sample = (case.get("eval_samples") or [{}])[0]
        labels = {
            str(label.get("point_id") or ""): label
            for label in (sample.get("no_human_v1_5_labels") if isinstance(sample, dict) else []) or []
        }
        for point in case.get("gold_scoring_points") or []:
            key = (str(case.get("case_id") or ""), str(point.get("point_id") or ""))
            rows.append(
                _point_row(
                    case=case,
                    point=point,
                    sample=sample if isinstance(sample, dict) else None,
                    label=labels.get(str(point.get("point_id") or "")),
                    corpus=corpus,
                    previous=previous.get(key),
                )
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: json.dumps(row.get(field), ensure_ascii=False)
                    if isinstance(row.get(field), (dict, list))
                    else row.get(field)
                    for field in fields
                }
            )


def _short_common_disposition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    disposition: list[dict[str, Any]] = []
    for row in rows:
        display_terms = [str(term) for term in row.get("display_terms") or []]
        required_terms = [str(term) for term in row.get("required_terms") or []]
        short_terms = [term for term in display_terms if _is_short_common_single_term(term)]
        if short_terms or any(term != old for term in required_terms for old in short_terms):
            disposition.append(
                {
                    "case_id": row.get("case_id"),
                    "point_id": row.get("point_id"),
                    "short_common_terms": short_terms,
                    "required_terms": required_terms,
                    "anchor_source": row.get("anchor_source"),
                    "chunk_id": row.get("chunk_id"),
                    "textbook_quote": row.get("textbook_quote"),
                    "status": "unresolved" if short_terms else "repaired_or_not_applicable",
                }
            )
    return disposition


def _r5_audit_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority: list[dict[str, Any]] = []
    for row in rows:
        if row.get("rescued_from_r5") or row.get("rescued_from_r4") or row.get("case_id") in {"Q3-1A433000", "Q9-1A434000", "Q11-1A434020"}:
            priority.append(row)
    priority.extend(row for row in rows if row.get("anchor_source") != "textbook")
    priority.extend(row for row in rows if row.get("anchor_source") == "textbook")
    seen: set[tuple[str, str]] = set()
    selected: list[dict[str, Any]] = []
    for row in priority:
        key = (str(row.get("case_id") or ""), str(row.get("point_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= 24:
            break
    return selected


def _r5_finding(result: dict[str, Any], rows: list[dict[str, Any]], three_arm_path: str = "", *, stage: str = "r5") -> str:
    point_summary = result.get("point_summary") or {}
    anchor_counts = point_summary.get("anchor_source_counts") or {}
    point_type_counts = point_summary.get("point_type_counts") or {}
    rescued_key = "rescued_from_r5" if stage == "r6" else "rescued_from_r4"
    rescued = [row for row in rows if row.get(rescued_key)]
    weak = [row for row in rows if row.get("point_type") == "text_term" and row.get("anchor_source") != "textbook"]
    invalid_textbook = [row for row in rows if row.get("anchor_source") == "textbook" and not row.get("verified_in_content_markdown")]
    short_common = [
        row
        for row in rows
        if len(row.get("required_terms") or []) == 1 and _is_short_common_single_term(str((row.get("required_terms") or [""])[0]))
    ]
    lines = [
        "# FINDING: no-human v1.5 r6 rubric-to-textbook-term repair"
        if stage == "r6"
        else "# FINDING: no-human v1.5 r5 per-term textbook anchor repair",
        "",
        "- status: `directional_shadow_pilot_gate`",
        "- runtime boundary: no RAG, no production gate, no CaseGradingSkillKernel authority change.",
        "- r6 change: targeted rubric/display sentences are compiled to distinctive textbook terms before verify-on-write."
        if stage == "r6"
        else "- r5 change: source anchoring is per-term; point-level textbook certification survives when at least one distinctive child term verifies in content_markdown.",
        "",
        "## Hard Gate",
        "",
        f"- point_count: `{point_summary.get('point_count')}`",
        f"- point_type_counts: `{json.dumps(point_type_counts, ensure_ascii=False)}`",
        f"- anchor_source_counts: `{json.dumps(anchor_counts, ensure_ascii=False)}`",
        f"- textbook_anchor_point_ratio: `{point_summary.get('textbook_anchor_point_ratio')}`",
        f"- invalid_textbook_anchors: `{len(invalid_textbook)}`",
        f"- short_common_single_anchors: `{len(short_common)}`",
        f"- {'r5_to_r6' if stage == 'r6' else 'r4_to_r5'}_rescued_textbook_points: `{len(rescued)}`",
        f"- three_arm_rerun: `{three_arm_path or 'pending'}`",
        "",
        "## Rescued From r5" if stage == "r6" else "## Rescued From r4",
        "",
    ]
    if rescued:
        for row in rescued:
            lines.append(
                f"- `{row.get('case_id')}::{row.get('point_id')}` previous=`{row.get('previous_anchor_source')}` -> {stage}=`{row.get('anchor_source')}` quote=`{row.get('textbook_quote')}` terms=`{json.dumps(row.get('required_terms') or [], ensure_ascii=False)}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Still Weak Text Terms", ""])
    if weak:
        for row in weak:
            term_sources = {
                term: data.get("anchor_source")
                for term, data in (row.get("term_anchor_map") or {}).items()
                if isinstance(data, dict)
            }
            lines.append(
                f"- `{row.get('case_id')}::{row.get('point_id')}` source=`{row.get('anchor_source')}` terms=`{json.dumps(term_sources, ensure_ascii=False)}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Invalid / Short Common Details", ""])
    lines.append(f"- invalid_textbook_anchor_rows: `{json.dumps(invalid_textbook, ensure_ascii=False)}`")
    lines.append(f"- short_common_single_anchor_rows: `{json.dumps(short_common, ensure_ascii=False)}`")
    return "\n".join(lines) + "\n"


def _render_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    point_summary = result.get("point_summary") or {}
    comparison = result.get("v0_vs_v1_5_comparison") or {}
    lines = [
        "# Luban No-Human v1.5 Textbook-Anchored Golden",
        "",
        "- status: `textbook_anchored_auditable_no_human_v1_5_shadow`",
        "- claim boundary: pure literal textbook-term points are auditable; residual points remain directional.",
        "- not human IRR; not production gate.",
        "",
        "## Fixture Summary",
        "",
        f"- cases: `{summary['cases']}`",
        f"- samples: `{summary['samples']}`",
        f"- point_labels: `{summary['point_labels']}`",
        f"- deterministic_point_labels: `{summary['deterministic_point_labels']}`",
        f"- deterministic_ratio: `{summary['deterministic_ratio']}`",
        f"- residual_counts: `{json.dumps(summary['residual_counts'], ensure_ascii=False)}`",
        f"- resolution_counts: `{json.dumps(summary['resolution_counts'], ensure_ascii=False)}`",
        f"- po_workload_ratio: `{summary['po_workload_ratio']}`",
        f"- external_expert_necessity_ratio: `{summary['external_expert_necessity_ratio']}`",
        f"- R7a_PO_self_decision_queue: `{result.get('human_escalation_queue_counts', {}).get('R7a_PO_self_decision')}`",
        f"- R7b_external_expert_last_resort_queue: `{result.get('human_escalation_queue_counts', {}).get('R7b_external_expert_last_resort')}`",
        f"- unanchored_root_cause_counts: `{json.dumps(result.get('unanchored_root_cause_counts') or {}, ensure_ascii=False)}`",
        f"- independent_triage_counts: `{json.dumps((result.get('independent_triage') or {}).get('counts') or {}, ensure_ascii=False)}`",
        f"- point_type_counts: `{json.dumps(point_summary.get('point_type_counts') or {}, ensure_ascii=False)}`",
        f"- anchor_source_counts: `{json.dumps(point_summary.get('anchor_source_counts') or {}, ensure_ascii=False)}`",
        f"- textbook_anchor_point_ratio: `{point_summary.get('textbook_anchor_point_ratio')}`",
        "",
        "## v0 vs v1.5 Deterministic Subset",
        "",
    ]
    if comparison.get("available"):
        lines.extend(
            [
                "| arm | samples | mean abs delta v1.5 | mean abs delta v0 same subset |",
                "|---|---:|---:|---:|",
            ]
        )
        for arm, data in sorted((comparison.get("summary") or {}).items()):
            lines.append(
                f"| {arm} | {data['sample_count']} | {data['mean_abs_score_delta_v1_5']} | {data['mean_abs_score_delta_v0_same_subset']} |"
            )
    else:
        lines.append(f"- comparison unavailable: `{comparison.get('reason')}`")
    lines.extend(
        [
            "",
            "## Three Golden Layers",
            "",
            "| layer | anchor | can claim | cannot claim |",
            "|---|---|---|---|",
            "| v0 AI-ledger | AI construction ledger | directional grader-vs-construction-intent signal | accuracy / production gate |",
            "| no-human v1.5 | textbook / standard exact spans | auditable literal-term subset metrics | human IRR / production gate |",
            "| human v1 | double-blind expert IRR | production-gate evidence after reliability gate | unavailable until humans label |",
        ]
    )
    return "\n".join(lines) + "\n"


def build_no_human_v1_5_bundle(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_fixture_path: Path = DEFAULT_OUTPUT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    prior_report_path: Path | None = DEFAULT_PRIOR_REPORT,
    agent_a_labels_path: Path | None = DEFAULT_AGENT_A_LABELS,
    agent_b_labels_path: Path | None = DEFAULT_AGENT_B_LABELS,
) -> dict[str, Any]:
    source_root = Path(source_root).expanduser().resolve()
    fixture = _read_json(Path(fixture_path))
    corpus = build_textbook_anchor_corpus(source_root)
    previous_summary_path = output_dir / "no_human_v1_5_summary.json"
    previous_summary = _read_json(previous_summary_path).get("summary") if previous_summary_path.exists() else None
    output = dict(fixture)
    output["suite"] = "luban_case_grading_golden_no_human_v1_5"
    output["status"] = "textbook_anchored_auditable_no_human_v1_5_corrected_shadow"
    output["version"] = "no_human_v1_5_content_markdown_reanchor_r3"
    output["golden_layer"] = {
        "name": "textbook_anchored_auditable_no_human_v1_5",
        "source_root": str(source_root),
        "source_dirs": ["2026教材/第二次加强"],
        "claim_boundary": "Textbook literal-term anchors come from content_markdown only; calculation and figure points are not counted as textbook-term certification. Not human IRR and not production gate.",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "corpus_record_count": len(corpus),
    }
    cases: list[dict[str, Any]] = []
    all_agreements: list[dict[str, Any]] = []
    all_root_counts: dict[str, int] = {}
    for case in fixture.get("cases") or []:
        case_copy = dict(case)
        has_figure_points = any(_is_figure_point(point) for point in case.get("gold_scoring_points") or [])
        case_corpus = _case_scoped_corpus(corpus, case)
        if has_figure_points:
            case_corpus = case_corpus + build_case_exam_figure_corpus(case)
        case_corpus = case_corpus + build_case_official_answer_corpus(case)
        terms_by_point, squeeze_by_point, metadata_by_point, root_counts = _required_terms_by_point(case, case_corpus)
        for category, count in root_counts.items():
            all_root_counts[category] = all_root_counts.get(category, 0) + int(count)
        new_points = []
        label_points = []
        for point in case.get("gold_scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            meta = metadata_by_point.get(point_id, {})
            enriched_point = {
                **point,
                "point_type": meta.get("point_type") or "text_term",
                "anchor_source": meta.get("anchor_source") or "non_textbook",
                "chunk_id": meta.get("chunk_id") or "",
                "textbook_quote": meta.get("textbook_quote") or "",
                "term_anchor_map": meta.get("term_anchor_map") or {},
                "calculation_expected_terms_v1_5": meta.get("calculation_expected_terms_v1_5") or [],
            }
            label_points.append(enriched_point)
            new_points.append(
                {
                    **enriched_point,
                    "required_terms_v1_5": terms_by_point.get(point_id, []),
                    "display_terms_v1_5": meta.get("display_terms", terms_by_point.get(point_id, [])),
                    "term_squeeze_v1_5": squeeze_by_point.get(point_id, {}),
                    "textbook_provenance": meta.get("provenance") or {},
                }
            )
        case_for_labels = {**case, "gold_scoring_points": label_points}
        labels = build_no_human_labels_for_case(case=case_for_labels, corpus=case_corpus, required_terms_by_point=terms_by_point)
        all_agreements.append({"case_id": case.get("case_id"), **labels["agent_agreement"]})
        new_samples = []
        for sample in case.get("eval_samples") or []:
            sample_id = str(sample.get("student_id") or "")
            new_samples.append({**sample, "no_human_v1_5_labels": labels["labels_by_sample"].get(sample_id, [])})
        case_copy["gold_scoring_points"] = new_points
        case_copy["eval_samples"] = new_samples
        cases.append(case_copy)
    output["cases"] = cases
    output["no_human_v1_5_agreement"] = {
        "meaning": "process reproducibility between two isolated deterministic role implementations; not human IRR",
        "by_case": all_agreements,
    }
    human_escalation_queues = build_human_escalation_queues(output)
    independent_triage: dict[str, Any] = {"available": False, "reason": "missing_independent_agent_labels"}
    if (
        agent_a_labels_path
        and agent_b_labels_path
        and Path(agent_a_labels_path).exists()
        and Path(agent_b_labels_path).exists()
    ):
        labels_a = _read_json(Path(agent_a_labels_path))
        labels_b = _read_json(Path(agent_b_labels_path))
        independent_triage = merge_independent_resolution_labels(
            human_escalation_queues["R7a_PO_self_decision"],
            labels_a,
            labels_b,
        )
        independent_triage["available"] = True
        independent_triage["agent_a_labels_path"] = str(agent_a_labels_path)
        independent_triage["agent_b_labels_path"] = str(agent_b_labels_path)
        output = apply_resolution_merge_to_fixture(output, independent_triage)
        human_escalation_queues = build_human_escalation_queues(output)
    summary = summarize_no_human_fixture(output)
    point_summary = _point_count_summary(output)
    comparison = _compare_prior_report(prior_report_path, output)
    result = {
        "fixture_path": str(output_fixture_path),
        "report_path": str(output_dir / "no_human_v1_5_report.md"),
        "summary_path": str(output_dir / "no_human_v1_5_summary.json"),
        "po_queue_path": str(output_dir / "R7a_PO_self_decision_queue.json"),
        "external_expert_queue_path": str(output_dir / "R7b_external_expert_last_resort_queue.json"),
        "summary": summary,
        "point_summary": point_summary,
        "previous_summary": previous_summary,
        "unanchored_root_cause_counts": all_root_counts,
        "independent_triage": {
            key: value
            for key, value in independent_triage.items()
            if key != "rows"
        },
        "human_escalation_queue_counts": {
            "R7a_PO_self_decision": len(human_escalation_queues["R7a_PO_self_decision"]),
            "R7b_external_expert_last_resort": len(human_escalation_queues["R7b_external_expert_last_resort"]),
        },
        "v0_vs_v1_5_comparison": comparison,
    }
    _write_json(output_fixture_path, output)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "no_human_v1_5_summary.json", result)
    _write_json(output_dir / "R7a_PO_self_decision_queue.json", human_escalation_queues["R7a_PO_self_decision"])
    _write_json(output_dir / "R7b_external_expert_last_resort_queue.json", human_escalation_queues["R7b_external_expert_last_resort"])
    if independent_triage.get("available"):
        _write_json(output_dir / "independent_triage_merge.json", independent_triage)
    stage = _artifact_stage(output_dir)
    point_rows = _point_classification_rows(output, corpus, stage=stage)
    point_classification_json = output_dir / f"point_classification_{stage}_20260602.json"
    point_classification_csv = output_dir / f"point_classification_{stage}_20260602.csv"
    audit_samples_json = output_dir / f"anchor_audit_samples_{stage}_20260602.json"
    finding_path = (
        output_dir / "FINDING_rubric_to_textbook_r6.md"
        if stage == "r6"
        else output_dir / "FINDING_per_term_anchor_r5.md"
    )
    _write_json(point_classification_json, point_rows)
    _write_csv(
        point_classification_csv,
        point_rows,
        [
            "case_id",
            "point_id",
            "point_type",
            "anchor_source",
            "chunk_id",
            "textbook_quote",
            "verified_in_content_markdown",
            "required_terms",
            "display_terms",
            "term_anchor_map",
            "previous_anchor_source",
            "rescued_from_r4",
            "rescued_from_r5",
            "sample_hit",
            "sample_score",
            "sample_resolution_class",
            "label",
        ],
    )
    _write_json(audit_samples_json, _r5_audit_samples(point_rows))
    _write_json(output_dir / "short_common_anchor_disposition_20260602.json", _short_common_disposition(point_rows))
    (output_dir / "no_human_v1_5_report.md").write_text(_render_report(result), encoding="utf-8")
    (finding_path).write_text(_r5_finding(result, point_rows, stage=stage), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Luban textbook-anchored auditable no-human v1.5 golden.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--output-fixture", default=str(DEFAULT_OUTPUT_FIXTURE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prior-report", default=str(DEFAULT_PRIOR_REPORT))
    parser.add_argument("--agent-a-labels", default="")
    parser.add_argument("--agent-b-labels", default="")
    args = parser.parse_args()
    result = build_no_human_v1_5_bundle(
        fixture_path=Path(args.fixture),
        source_root=Path(args.source_root),
        output_fixture_path=Path(args.output_fixture),
        output_dir=Path(args.output_dir),
        prior_report_path=Path(args.prior_report) if args.prior_report else None,
        agent_a_labels_path=Path(args.agent_a_labels) if args.agent_a_labels else None,
        agent_b_labels_path=Path(args.agent_b_labels) if args.agent_b_labels else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
