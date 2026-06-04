"""M3.5 blocked-point rubric normalization factory.

This is an offline deterministic normalizer. It turns blocked rubric points into
structured candidates for later source-hunt and AI Expert Council review.

Hard boundaries:
- no live LLM calls;
- official_answer/explanation is only a rubric-structure seed, never source authority;
- normalized candidates are not verified and never auto-certifiable;
- no formal registry, runtime, DB, RAG, web, BI, or billing writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts/luban_grading_artifacts"
OUT_DIR = ARTIFACT_ROOT / "blocked_point_rubric_normalization_m35_20260604"
M5_DIR = ARTIFACT_ROOT / "case_rubric_authority_adjudication_m5_20260604"
M3_DIR = ARTIFACT_ROOT / "case_rubric_structuring_m3_20260604"
M5D_DIR = ARTIFACT_ROOT / "ai_expert_council_source_court_m5d_20260604"
M7_REPAIR_DIR = ARTIFACT_ROOT / "registry_v1_source_repair_factory_m7_20260604"
M7_COUNCIL_DIR = ARTIFACT_ROOT / "registry_v1_council_hardened_candidate_m7_20260604"
OFFICIAL_BANK_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"
)

REQUIRED_OUTPUTS = [
    "normalization_workflow_manifest.json",
    "unified_blocked_point_backlog.json",
    "blocked_point_normalization_inventory.json",
    "normalized_rubric_candidates.jsonl",
    "split_point_proposals.jsonl",
    "rejected_normalization_variants.jsonl",
    "normalization_quality_report.json",
    "source_hunt_query_terms.jsonl",
    "m7_rerun_readiness_report.json",
    "compiler_hard_gate_compatibility_report.json",
    "FINDING_blocked_point_rubric_normalization_m35_20260604.md",
]

MIN_TERM_LEN = 4

_LIST_MARKER = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?<![0-9A-Za-z])(?:[1-9]|1[0-9])\s*[.、)]")
_SENT_SPLIT = re.compile(r"[；;。\n]")
_ITEM_SPLIT = re.compile(r"[，,、；;。\n]")
_FORMULA = re.compile(r"([\w一-龥()（）+\-*/×÷. ]{0,16}[=＝]\s*[-+*/×÷().\d\s]+[=＝]\s*[\d.]+)")
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_UNIT = re.compile(r"(万元|元|个月|月|天|日|m³|m3|m²|m2|㎡|m\b|kg|t\b|%|分)")
_GENERIC_TERMS = {
    "内容",
    "包括",
    "措施",
    "要求",
    "方法",
    "原则",
    "情况",
    "做法",
    "如下",
    "正确",
    "错误",
    "不妥",
    "符合",
    "规定",
    "应",
    "不应",
}
_DROP_PATTERNS = [
    re.compile(r"^\s*[（(]?\s*注\s*[：:]"),
    re.compile(r"^\s*理由\s*[：:]"),
    re.compile(r"^\s*不妥之处[一二三四五六七八九十0-9]*\s*[：:]?$"),
    re.compile(r"^\s*不正确\s*[。.]?$"),
    re.compile(r"^\s*正确\s*[。.]?$"),
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(body + ("\n" if body else ""), "utf-8")


def _norm(text: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’]", "", str(text or ""))


def _fingerprint(question_id: str, point_id: str, label: str) -> str:
    raw = f"{question_id}|{point_id}|{_norm(label)[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _is_drop_like(text: str) -> bool:
    compact = str(text or "").strip()
    return any(pattern.search(compact) for pattern in _DROP_PATTERNS)


def _load_m5_points() -> dict[tuple[str, str], dict[str, Any]]:
    data = _read_json(M5_DIR / "authority_adjudication.json")
    return {(p["question_id"], p["point_id"]): p for p in data.get("points", [])}


def _load_m3_points() -> dict[tuple[str, str], dict[str, Any]]:
    points = _read_json(M3_DIR / "scoring_point_candidates.json")
    return {(p["question_id"], p["point_id"]): p for p in points}


def _load_m5d_point_decisions() -> dict[tuple[str, str], dict[str, Any]]:
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for question in _read_json(M5D_DIR / "source_anchor_dispute_council_results.json"):
        for point in question.get("point_decisions", []):
            decisions[(question["question_id"], point["point_id"])] = point
    return decisions


def _merge_point_context(
    question_id: str,
    point_id: str,
    m5_points: dict[tuple[str, str], dict[str, Any]],
    m3_points: dict[tuple[str, str], dict[str, Any]],
    m5d_points: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    key = (question_id, point_id)
    m5 = m5_points.get(key, {})
    m3 = m3_points.get(key, {})
    m5d = m5d_points.get(key, {})
    label = (
        m5d.get("label_preview")
        or m5.get("label")
        or m3.get("label")
        or m3.get("official_answer_span")
        or m5.get("official_answer")
        or ""
    )
    official_span = m3.get("official_answer_span") or m5.get("official_answer") or label
    return {
        "question_id": question_id,
        "point_id": point_id,
        "point_label": label,
        "official_answer_span": official_span,
        "policy_type": m5.get("policy_type") or m3.get("policy_type") or m5d.get("policy_type") or "exact_required",
        "max_score": m5.get("max_score") or m3.get("max_score"),
        "node_code": m5.get("node_code") or "",
        "question_text": m5.get("question_text") or "",
        "source_exam": m5.get("source_exam") or "",
        "m5_decision": m5.get("point_authority_decision"),
        "source_status": m5.get("source_status_final") or m5.get("source_status"),
        "policy_gaps": m5.get("policy_gaps") or [],
        "m3_required_terms": m3.get("required_terms") or [],
        "m3_list_rule": m3.get("list_rule"),
        "m3_calculation_spec": m3.get("calculation_spec"),
        "m5d_council_action": m5d.get("council_action"),
        "m5d_source_verdict": m5d.get("source_verdict") or {},
        "m5d_aggregator_reason": m5d.get("aggregator_reason"),
    }


def build_unified_backlog() -> dict[str, Any]:
    m5_points = _load_m5_points()
    m3_points = _load_m3_points()
    m5d_points = _load_m5d_point_decisions()

    source_repair = _read_json(M7_REPAIR_DIR / "blocked_point_inventory.json").get("points", [])
    council = _read_json(M7_COUNCIL_DIR / "blocked_by_council_action.json").get("points", [])

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(row: dict[str, Any], priority: str, input_source: str) -> None:
        context = _merge_point_context(
            row["question_id"],
            row["point_id"],
            m5_points,
            m3_points,
            m5d_points,
        )
        label_hash = _fingerprint(context["question_id"], context["point_id"], context["point_label"])
        key = (context["question_id"], context["point_id"], label_hash)
        existing = by_key.get(key)
        merged_sources = set(existing.get("input_sources", [])) if existing else set()
        merged_sources.add(input_source)
        base = existing or context
        base.update(
            {
                "label_hash": label_hash,
                "priority": "P0" if priority == "P0" or base.get("priority") == "P0" else "P1",
                "input_sources": sorted(merged_sources),
                "m7_source_repair_category": row.get("category") or base.get("m7_source_repair_category"),
                "m7_source_repair_decision": row.get("decision") or base.get("m7_source_repair_decision"),
                "council_action": row.get("council_action") or base.get("council_action") or context.get("m5d_council_action"),
                "council_block_reason": row.get("block_reason") or base.get("council_block_reason"),
            }
        )
        by_key[key] = base

    for row in source_repair:
        add(row, "P1", "m7_source_repair_blocked_125")
    for row in council:
        add(row, "P0", "m7_council_blocked_19")

    points = sorted(by_key.values(), key=lambda p: (p["priority"] != "P0", p["question_id"], p["point_id"]))
    return {
        "input_counts": {
            "m7_source_repair_blocked_points": len(source_repair),
            "m7_council_blocked_points": len(council),
        },
        "deduped_count": len(points),
        "priority_counts": dict(Counter(p["priority"] for p in points)),
        "dedupe_key": "question_id + point_id + point_label_hash",
        "points": points,
    }


def _strip_meta(text: str) -> str:
    text = re.sub(r"[（(]\s*注[：:][^）)]*[）)]", "", text or "")
    text = re.sub(r"^\s*答\s*[：:]", "", text)
    return text.strip(" \n\t。；;，,")


def _split_items(text: str) -> list[str]:
    text = _strip_meta(text)
    if not text:
        return []
    pieces = [p for p in _LIST_MARKER.split(text) if p.strip()]
    if len(pieces) < 2:
        pieces = [p for p in _SENT_SPLIT.split(text) if p.strip()]
    items: list[str] = []
    for piece in pieces:
        piece = _strip_meta(piece)
        if not piece or _is_drop_like(piece):
            continue
        if len(_norm(piece)) < 3:
            continue
        items.append(piece[:120])
    return items


def _term_candidates(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    body = _strip_meta(text)
    if "：" in body or ":" in body:
        body = re.split(r"[：:]", body, maxsplit=1)[-1]
    for segment in _ITEM_SPLIT.split(body):
        segment = _strip_meta(segment).strip("等及和与的了")
        normalized = _norm(segment)
        if len(normalized) < MIN_TERM_LEN:
            continue
        if normalized in _GENERIC_TERMS:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(segment[:50])
    return terms[:10]


def _extract_required_terms(point: dict[str, Any], items: list[str]) -> list[str]:
    seed_terms = list(point.get("m3_required_terms") or [])
    seed_terms.extend(_term_candidates(point.get("official_answer_span") or point.get("point_label") or ""))
    for item in items:
        seed_terms.extend(_term_candidates(item))
    out: list[str] = []
    seen: set[str] = set()
    for term in seed_terms:
        term = _strip_meta(str(term)).strip("等及和与的了")
        normalized = _norm(term)
        if len(normalized) < MIN_TERM_LEN or normalized in _GENERIC_TERMS or normalized in seen:
            continue
        seen.add(normalized)
        out.append(term[:50])
    return out[:12]


def _calculation_spec(text: str) -> dict[str, Any] | None:
    formula_match = _FORMULA.search(text or "")
    numbers = _NUMBER.findall(text or "")
    unit_match = _UNIT.search(text or "")
    if not formula_match and not numbers:
        return None
    formula = formula_match.group(1).strip() if formula_match else None
    expected = None
    if formula:
        expected = re.split(r"[=＝]", formula)[-1].strip()
    elif numbers:
        expected = numbers[-1]
    return {
        "formula": formula,
        "expected_value": expected,
        "unit": unit_match.group(1) if unit_match else None,
        "machine_checkable": bool(formula and expected and unit_match),
    }


def _classify(point: dict[str, Any], items: list[str], terms: list[str], calc: dict[str, Any] | None) -> str:
    policy_type = point["policy_type"]
    council_action = point.get("council_action")
    label = point.get("point_label") or ""
    span = point.get("official_answer_span") or label
    gaps = set(point.get("policy_gaps") or [])
    repair_category = point.get("m7_source_repair_category")

    if council_action == "drop_point" or _is_drop_like(label):
        return "drop_point_candidate"
    if council_action == "require_external_source":
        return "external_source_needed"
    if council_action == "rewrite_point" or point.get("m5_decision") == "rewrite_needed":
        return "rewrite_needed"
    if council_action == "split_point":
        return "official_answer_blob_needs_split"
    if repair_category == "external_source_needed":
        return "external_source_needed" if not terms else (
            "official_answer_blob_needs_split" if len(items) >= 2 and policy_type != "list_rule" else "exact_required_missing_terms"
        )
    if policy_type == "figure_label":
        return "figure_label_not_runtime_safe"
    if policy_type == "semantic_allowed":
        return "semantic_allowed_not_runtime_safe"
    if policy_type == "penalty_rule":
        return "penalty_rule_missing_condition"
    if policy_type == "calculation":
        if not calc or not calc.get("formula"):
            return "calculation_missing_formula"
        if not calc.get("unit") or not calc.get("expected_value"):
            return "calculation_missing_unit_or_expected_value"
        return "calculation_missing_unit_or_expected_value" if not calc.get("machine_checkable") else "calculation_missing_formula"
    if policy_type == "list_rule":
        if "list_rule_without_denominator" in gaps:
            return "list_rule_missing_denominator"
        if len(items) < 2 and not point.get("m3_list_rule"):
            return "list_rule_missing_items"
        return "list_rule_missing_denominator"
    if len(items) >= 2 and len(_norm(span)) > 30:
        return "official_answer_blob_needs_split"
    return "exact_required_missing_terms"


def _list_spec(point: dict[str, Any], items: list[str]) -> dict[str, Any] | None:
    m3_rule = point.get("m3_list_rule") or {}
    raw_terms = m3_rule.get("terms") or []
    item_set = [str(x).strip() for x in raw_terms if len(_norm(x)) >= MIN_TERM_LEN]
    if len(item_set) < 2:
        item_set = [item for item in items if len(_norm(item)) >= MIN_TERM_LEN]
    if len(item_set) < 2:
        return None
    deduped: list[str] = []
    seen: set[str] = set()
    for item in item_set:
        normalized = _norm(item)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item[:80])
    return {"denominator": len(deduped), "item_set": deduped}


def _final_action(
    point: dict[str, Any],
    category: str,
    terms: list[str],
    list_spec: dict[str, Any] | None,
    calc: dict[str, Any] | None,
) -> str:
    council_action = point.get("council_action")
    if council_action == "drop_point" or category == "drop_point_candidate":
        return "drop_point"
    if council_action == "require_external_source" or category == "external_source_needed":
        return "require_external_source"
    if council_action == "keep_draft":
        return "keep_draft_unstructured"
    if council_action == "split_point" or category == "official_answer_blob_needs_split":
        return "split_into_multiple_points"
    if category in {"figure_label_not_runtime_safe", "semantic_allowed_not_runtime_safe", "rewrite_needed"}:
        return "keep_draft_unstructured"
    if point["policy_type"] == "list_rule" and list_spec:
        return "normalized_ready_for_source_hunt"
    if point["policy_type"] == "calculation" and calc and calc.get("machine_checkable"):
        return "normalized_ready_for_source_hunt"
    if point["policy_type"] in {"exact_required", "penalty_rule"} and terms:
        return "normalized_ready_for_source_hunt"
    if category.startswith("calculation_"):
        return "keep_draft_unstructured"
    return "require_external_source" if not terms else "keep_draft_unstructured"


def _normalize_point(point: dict[str, Any]) -> dict[str, Any]:
    text = point.get("official_answer_span") or point.get("point_label") or ""
    items = _split_items(text)
    terms = _extract_required_terms(point, items)
    calc = _calculation_spec(text) if point["policy_type"] == "calculation" else None
    list_spec = _list_spec(point, items) if point["policy_type"] == "list_rule" else None
    category = _classify(point, items, terms, calc)
    action = _final_action(point, category, terms, list_spec, calc)

    search_terms = list_spec["item_set"] if list_spec else terms[:]
    if calc:
        for value in [calc.get("formula"), calc.get("expected_value"), calc.get("unit")]:
            if value and str(value) not in search_terms:
                search_terms.append(str(value))

    m7_hard_gate = {
        "list_rule_coverage_ready": bool(point["policy_type"] != "list_rule" or list_spec),
        "calculation_spec_ready": bool(point["policy_type"] != "calculation" or (calc and calc.get("machine_checkable"))),
        "source_hunt_only": True,
        "auto_certifiable_after_normalization": False,
        "requires_future_textbook_exact_match": True,
    }
    skeptic_flags: list[str] = []
    if action == "normalized_ready_for_source_hunt" and not search_terms:
        skeptic_flags.append("ready_without_query_terms")
    if point["policy_type"] == "exact_required" and not terms:
        skeptic_flags.append("exact_required_without_required_terms")
    if point["policy_type"] == "list_rule" and not list_spec:
        skeptic_flags.append("list_rule_without_denominator_or_item_set")
    if point["policy_type"] == "calculation" and not (calc and calc.get("machine_checkable")):
        skeptic_flags.append("calculation_without_machine_checkable_spec")
    if _is_drop_like(point.get("point_label", "")):
        skeptic_flags.append("prompt_or_error_restatement_not_scoring_point")

    return {
        "question_id": point["question_id"],
        "point_id": point["point_id"],
        "priority": point["priority"],
        "input_sources": point.get("input_sources", []),
        "point_label": point.get("point_label"),
        "official_answer_span": text,
        "policy_type": point["policy_type"],
        "max_score": point.get("max_score"),
        "category": category,
        "final_action": action,
        "required_terms": terms,
        "list_rule": list_spec,
        "list_spec": list_spec,
        "calculation_spec": calc,
        "penalty_rule": None,
        "source_hunt_query_terms": search_terms[:12],
        "source_status": "candidate_unverified",
        "anchor_source": "none",
        "verified": False,
        "auto_certifiable": False,
        "runtime_auto_certifiable": False,
        "human_reviewed": False,
        "review_source": "deterministic_rubric_normalization_m35",
        "structure_from": "official_answer_rubric_structure_candidate_not_source",
        "m7_hard_gate": m7_hard_gate,
        "council_action": point.get("council_action"),
        "council_block_reason": point.get("council_block_reason"),
        "skeptic_flags": skeptic_flags,
        "node_code": point.get("node_code") or "",
    }


def _split_proposals(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    if candidate["final_action"] != "split_into_multiple_points":
        return []
    items = _split_items(candidate.get("official_answer_span") or candidate.get("point_label") or "")
    if not items and candidate.get("list_rule"):
        items = candidate["list_rule"]["item_set"]
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(items[:10], start=1):
        terms = _term_candidates(item)
        if not terms and len(_norm(item)) >= MIN_TERM_LEN:
            terms = [item[:50]]
        proposals.append(
            {
                "question_id": candidate["question_id"],
                "parent_point_id": candidate["point_id"],
                "split_point_id": f"{candidate['point_id']}.s{index}",
                "policy_type": "exact_required",
                "label": item[:100],
                "required_terms": terms[:6],
                "source_hunt_query_terms": terms[:6] or [item[:80]],
                "source_status": "candidate_unverified",
                "verified": False,
                "auto_certifiable": False,
                "runtime_auto_certifiable": False,
                "human_reviewed": False,
            }
        )
    return proposals


def _quality_report(candidates: list[dict[str, Any]], splits: list[dict[str, Any]]) -> dict[str, Any]:
    exact = [c for c in candidates if c["policy_type"] == "exact_required"]
    list_rules = [c for c in candidates if c["policy_type"] == "list_rule"]
    calculations = [c for c in candidates if c["policy_type"] == "calculation"]
    return {
        "total_candidates": len(candidates),
        "action_counts": dict(Counter(c["final_action"] for c in candidates)),
        "category_counts": dict(Counter(c["category"] for c in candidates)),
        "required_terms": {
            "exact_required_total": len(exact),
            "exact_required_with_required_terms": sum(1 for c in exact if c["required_terms"]),
            "coverage": round((sum(1 for c in exact if c["required_terms"]) / len(exact)), 4) if exact else None,
        },
        "list_rule": {
            "list_rule_total": len(list_rules),
            "with_denominator_and_item_set": sum(1 for c in list_rules if c["list_rule"]),
            "coverage": round((sum(1 for c in list_rules if c["list_rule"]) / len(list_rules)), 4) if list_rules else None,
        },
        "calculation_spec": {
            "calculation_total": len(calculations),
            "with_machine_checkable_spec": sum(
                1 for c in calculations if c["calculation_spec"] and c["calculation_spec"].get("machine_checkable")
            ),
            "coverage": round(
                (
                    sum(1 for c in calculations if c["calculation_spec"] and c["calculation_spec"].get("machine_checkable"))
                    / len(calculations)
                ),
                4,
            )
            if calculations
            else None,
        },
        "split_candidates_created": len(splits),
        "official_answer_blob_remaining_count": sum(
            1 for c in candidates if len(_norm(c.get("official_answer_span"))) > 120 and c["final_action"] != "split_into_multiple_points"
        ),
        "generic_required_terms_flags": sum(
            1
            for c in candidates
            if c["required_terms"] and all(_norm(term) in _GENERIC_TERMS for term in c["required_terms"])
        ),
    }


def _readiness_report(
    candidates: list[dict[str, Any]],
    splits: list[dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, Any]:
    actions = Counter(c["final_action"] for c in candidates)
    ready = actions.get("normalized_ready_for_source_hunt", 0)
    split = actions.get("split_into_multiple_points", 0)
    verdict = "GO" if ready >= 60 and split >= 10 else ("WEAK-GO" if ready + len(splits) > 0 else "NO-GO")
    return {
        "m7_source_hunt_rerun_condition": verdict,
        "m7_rerun_ready": verdict in {"GO", "WEAK-GO"},
        "normalized_ready_for_source_hunt": ready,
        "split_into_multiple_points": split,
        "split_candidates_created": len(splits),
        "keep_draft_unstructured": actions.get("keep_draft_unstructured", 0),
        "require_external_source": actions.get("require_external_source", 0),
        "drop_point": actions.get("drop_point", 0),
        "reason": (
            "structured query terms exist, but normalized candidates are unverified and must go through source hunt"
            if verdict == "WEAK-GO"
            else "sufficient normalized supply for source hunt"
            if verdict == "GO"
            else "no structured source hunt supply"
        ),
        "coverage_snapshot": quality,
    }


def _compiler_report(candidates: list[dict[str, Any]], splits: list[dict[str, Any]]) -> dict[str, Any]:
    official_upgrades = sum(1 for c in candidates if c["source_status"] == "verified_textbook")
    auto_count = sum(1 for c in candidates if c["auto_certifiable"] or c["runtime_auto_certifiable"])
    human_true = sum(1 for c in candidates if c["human_reviewed"])
    split_auto = sum(1 for s in splits if s["auto_certifiable"] or s["runtime_auto_certifiable"])
    return {
        "m7_compatible": official_upgrades == 0 and auto_count == 0 and human_true == 0 and split_auto == 0,
        "list_rule_requires_coverage_1_0": True,
        "council_final_action_gate_enforced": True,
        "repaired_anchor_deterministic_reverify_required": True,
        "normalized_points_auto_certifiable": auto_count,
        "split_points_auto_certifiable": split_auto,
        "official_answer_upgraded_to_textbook_source": official_upgrades,
        "human_reviewed_true_count": human_true,
        "formal_registry_emitted": False,
        "runtime_connected": False,
        "forbidden_actions_blocked_from_auto": [
            "split_point",
            "require_external_source",
            "rewrite_point",
            "drop_point",
            "keep_draft",
            "council_not_publish",
        ],
    }


def build_m35(out_dir: Path = OUT_DIR) -> tuple[dict[str, Any], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    backlog = build_unified_backlog()

    candidates: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    query_terms: list[dict[str, Any]] = []
    inventory_points: list[dict[str, Any]] = []

    for point in backlog["points"]:
        candidate = _normalize_point(point)
        point["category"] = candidate["category"]
        point["final_action"] = candidate["final_action"]
        candidates.append(candidate)
        point_splits = _split_proposals(candidate)
        splits.extend(point_splits)
        inventory_points.append(
            {
                "question_id": candidate["question_id"],
                "point_id": candidate["point_id"],
                "priority": candidate["priority"],
                "policy_type": candidate["policy_type"],
                "category": candidate["category"],
                "final_action": candidate["final_action"],
                "council_action": candidate.get("council_action"),
            }
        )
        if candidate["skeptic_flags"] or candidate["final_action"] in {
            "keep_draft_unstructured",
            "require_external_source",
            "drop_point",
        }:
            rejected.append(
                {
                    "question_id": candidate["question_id"],
                    "point_id": candidate["point_id"],
                    "category": candidate["category"],
                    "final_action": candidate["final_action"],
                    "reason": candidate["skeptic_flags"] or [candidate["final_action"]],
                    "variant_status": "rejected_or_not_ready_for_source_hunt",
                }
            )
        if candidate["source_hunt_query_terms"]:
            query_terms.append(
                {
                    "question_id": candidate["question_id"],
                    "point_id": candidate["point_id"],
                    "priority": candidate["priority"],
                    "policy_type": candidate["policy_type"],
                    "final_action": candidate["final_action"],
                    "node_code": candidate.get("node_code"),
                    "source_hunt_query_terms": candidate["source_hunt_query_terms"],
                }
            )

    quality = _quality_report(candidates, splits)
    readiness = _readiness_report(candidates, splits, quality)
    compiler = _compiler_report(candidates, splits)
    actions = Counter(c["final_action"] for c in candidates)
    categories = Counter(c["category"] for c in candidates)

    # Hard invariants.
    for candidate in candidates:
        assert candidate["source_status"] == "candidate_unverified"
        assert candidate["verified"] is False
        assert candidate["auto_certifiable"] is False
        assert candidate["runtime_auto_certifiable"] is False
        assert candidate["human_reviewed"] is False
    for split in splits:
        assert split["source_status"] == "candidate_unverified"
        assert split["auto_certifiable"] is False
        assert split["runtime_auto_certifiable"] is False

    manifest = {
        "stage": "M3.5 Rubric Normalization Factory",
        "generated_by": "scripts/build_luban_blocked_point_rubric_normalization_m35.py",
        "deterministic_parser_only": True,
        "live_llm_api_called": False,
        "secret_printed": False,
        "input_artifacts": {
            "m7_source_repair": str(M7_REPAIR_DIR.relative_to(REPO)),
            "m7_council_hardened": str(M7_COUNCIL_DIR.relative_to(REPO)),
            "m5_authority": str(M5_DIR.relative_to(REPO)),
            "m3_structuring": str(M3_DIR.relative_to(REPO)),
            "m5d_source_court": str(M5D_DIR.relative_to(REPO)),
            "official_bank_root": str(OFFICIAL_BANK_ROOT),
        },
        "no_runtime_kernel_rag_db_web_bi_billing_changes": True,
        "official_answer_is_textbook_source": False,
        "official_answer_is_source_authority": False,
        "normalized_candidate_is_verified": False,
        "normalized_candidate_auto_certifiable": False,
        "formal_registry_emitted": False,
        "human_reviewed": False,
        "required_outputs": REQUIRED_OUTPUTS,
    }
    inventory = {
        "count": len(candidates),
        "category_counts": dict(categories),
        "action_counts": dict(actions),
        "priority_counts": dict(Counter(c["priority"] for c in candidates)),
        "p1_broader_category_counts": dict(
            Counter(c["category"] for c in candidates if c["priority"] == "P1")
        ),
        "p1_broader_action_counts": dict(
            Counter(c["final_action"] for c in candidates if c["priority"] == "P1")
        ),
        "p0_council_action_counts": dict(
            Counter(c["final_action"] for c in candidates if c["priority"] == "P0")
        ),
        "points": inventory_points,
    }

    _write_json(out_dir / "normalization_workflow_manifest.json", manifest)
    _write_json(out_dir / "unified_blocked_point_backlog.json", backlog)
    _write_json(out_dir / "blocked_point_normalization_inventory.json", inventory)
    _write_jsonl(out_dir / "normalized_rubric_candidates.jsonl", candidates)
    _write_jsonl(out_dir / "split_point_proposals.jsonl", splits)
    _write_jsonl(out_dir / "rejected_normalization_variants.jsonl", rejected)
    _write_json(out_dir / "normalization_quality_report.json", quality)
    _write_jsonl(out_dir / "source_hunt_query_terms.jsonl", query_terms)
    _write_json(out_dir / "m7_rerun_readiness_report.json", readiness)
    _write_json(out_dir / "compiler_hard_gate_compatibility_report.json", compiler)
    (out_dir / "FINDING_blocked_point_rubric_normalization_m35_20260604.md").write_text(
        _finding(backlog, inventory, quality, readiness, compiler, splits),
        "utf-8",
    )

    return {
        "actions": dict(actions),
        "categories": dict(categories),
        "coverage": {
            "exact_required_total": quality["required_terms"]["exact_required_total"],
            "exact_required_with_required_terms": quality["required_terms"]["exact_required_with_required_terms"],
            "list_rule_total": quality["list_rule"]["list_rule_total"],
            "list_rule_with_denominator": quality["list_rule"]["with_denominator_and_item_set"],
            "calculation_total": quality["calculation_spec"]["calculation_total"],
            "calculation_with_machine_checkable_spec": quality["calculation_spec"][
                "with_machine_checkable_spec"
            ],
        },
        "readiness": {
            "verdict": readiness["m7_source_hunt_rerun_condition"],
            **readiness,
        },
        "splits": len(splits),
        "normalized": candidates,
        "out_dir": str(out_dir),
    }


def _finding(
    backlog: dict[str, Any],
    inventory: dict[str, Any],
    quality: dict[str, Any],
    readiness: dict[str, Any],
    compiler: dict[str, Any],
    splits: list[dict[str, Any]],
) -> str:
    action_counts = inventory["action_counts"]
    category_counts = inventory["category_counts"]
    p1_category_counts = inventory["p1_broader_category_counts"]
    p1_action_counts = inventory["p1_broader_action_counts"]
    p0_points = [p for p in backlog["points"] if p["priority"] == "P0"]
    p0_lines = []
    for point in p0_points:
        p0_lines.append(
            f"- {point['question_id']} {point['point_id']}: council_action={point.get('council_action')}, "
            f"final_action={point.get('final_action', 'see inventory')}"
        )
    action_by_key = {(p["question_id"], p["point_id"]): p["final_action"] for p in inventory["points"]}
    p0_lines = []
    for point in p0_points:
        p0_lines.append(
            f"- {point['question_id']} {point['point_id']}: council_action={point.get('council_action')}, "
            f"final_action={action_by_key.get((point['question_id'], point['point_id']))}"
        )
    next_step = (
        "重跑 M7 source hunt"
        if readiness["m7_source_hunt_rerun_condition"] in {"GO", "WEAK-GO"}
        else "继续 M3.5 第二轮规范化"
    )
    return f"""# FINDING — Blocked Point Rubric Normalization M3.5（2026-06-04）

## 必答

1. unified backlog：输入 A=125（M7 Source Repair Factory blocked points），输入 B=19（M7 Council-Hardened council-blocked points），按 `question_id + point_id + point_label_hash` 去重后 **{backlog['deduped_count']}** 点；priority={backlog['priority_counts']}。
2. P0 council-blocked 19 点处理：
{chr(10).join(p0_lines)}
3. broader 125 blocked points 是否全部处理：YES。去重后 P1 broader 点 **{backlog['priority_counts'].get('P1', 0)}** 个；P1 category_counts={p1_category_counts}；P1 action_counts={p1_action_counts}。全量 category_counts={category_counts}。
4. normalized_ready_for_source_hunt：**{action_counts.get('normalized_ready_for_source_hunt', 0)}**。
5. split_into_multiple_points：**{action_counts.get('split_into_multiple_points', 0)}**；新增 split candidates **{len(splits)}**。
6. keep_draft_unstructured / require_external_source / drop：**{action_counts.get('keep_draft_unstructured', 0)} / {action_counts.get('require_external_source', 0)} / {action_counts.get('drop_point', 0)}**。
7. required_terms 覆盖率：exact_required **{quality['required_terms']['exact_required_with_required_terms']}/{quality['required_terms']['exact_required_total']}**，coverage={quality['required_terms']['coverage']}。
8. list_rule denominator + item set 覆盖率：**{quality['list_rule']['with_denominator_and_item_set']}/{quality['list_rule']['list_rule_total']}**，coverage={quality['list_rule']['coverage']}。
9. calculation_spec 覆盖率：**{quality['calculation_spec']['with_machine_checkable_spec']}/{quality['calculation_spec']['calculation_total']}**，coverage={quality['calculation_spec']['coverage']}。
10. 是否有 official_answer 被升为 textbook source：**NO**。所有 candidate `source_status=candidate_unverified`，official_answer 只作 rubric structure seed。
11. 是否有 normalized point 被设为 auto_certifiable：**NO**。normalized 与 split candidates 全部 `auto_certifiable=false` / `runtime_auto_certifiable=false`。
12. 是否兼容 M7 compiler hard gates：**YES**。`list_rule coverage==1.0` 只作为后续 source hunt/reverify 门；本轮不 auto，compiler report `m7_compatible={compiler['m7_compatible']}`。
13. M7 source hunt 是否具备重跑条件：**{readiness['m7_source_hunt_rerun_condition']}**。原因：{readiness['reason']}。
14. 下一步：**{next_step}**。本轮只补结构，不补 source；source hunt 仍必须逐字命中 2026 教材 content_markdown。
15. 单句总指挥建议：先用 M3.5 的 normalized/split/query-term 供给重跑 M7 source hunt；不要接 runtime，也不要把 official_answer 或 AI council 票当 source authority。

## 红线确认

- 不打印 secret。
- 未发起 live LLM。
- 不改 CaseGradingSkillKernel / RAG / runtime / DB / web / BI / billing。
- 不生成正式 registry。
- 不把 official_answer/explanation 当 textbook source。
- 不把 normalized candidate 当 verified。
- 不把任何 normalized point 设为 auto_certifiable。
- human_reviewed=false。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()
    result = build_m35(Path(args.out_dir))
    print(f"M3.5 normalization -> {args.out_dir}")
    print(f"actions={result['actions']}")
    print(f"categories={result['categories']}")
    print(f"readiness={result['readiness']['m7_source_hunt_rerun_condition']}")


if __name__ == "__main__":
    main()
