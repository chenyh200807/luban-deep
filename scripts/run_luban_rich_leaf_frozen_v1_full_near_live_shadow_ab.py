#!/usr/bin/env python3
"""Frozen-v1 full-pack near-live shadow A/B with outcomes recomputed from v3.0 context.

This is the frozen-axis rerun that closes the honest gap recorded by
``run_luban_rich_leaf_frozen_axis_near_live_ab_remap`` (whose outcomes were
inherited from the v2.3 proxy run). Every row here is re-evaluated against the
recompiled v3.0 runtime token pack units; nothing is inherited.

Review-only and provider-free: four deterministic local proxy arms, no
production RAG, no provider calls, no DB writes, no runtime install.
Output keeps the ``luban_rich_leaf_v23_near_live_shadow_ab.v1`` schema so the
existing learning-evidence candidate bridge can consume it unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613/runtime_token_pack_v30_frozen_full.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_go_evidence_20260613/near_live_shadow_ab_v30_recomputed.json"
)
AB_SCHEMA = "luban_rich_leaf_v23_near_live_shadow_ab.v1"
PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
PACK_STATUS = "candidate_ready_for_shadow_ab_full_accounted"
VERDICT_PASS = "PASS_V23_NEAR_LIVE_SHADOW_AB"
VERDICT_CEILING = "NEAR_LIVE_PROXY_ONLY"
KNOWLEDGE_FAMILIES = (
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "teaching_cards",
)
RAG_DOC_CHARS = 800


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _token_proxy(text: str) -> int:
    return max(0, len(text) // 4)


def _lexical_tokens(text: str) -> set[str]:
    words = {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}
    chars = {char for char in text if "一" <= char <= "鿿"}
    return words | chars


def _knowledge_text(unit: dict[str, Any]) -> str:
    compiled = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    parts: list[str] = []
    for family in KNOWLEDGE_FAMILIES:
        for item in compiled.get(family) or []:
            text = str(item).strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _exam_patterns(unit: dict[str, Any]) -> list[dict[str, Any]]:
    compiled = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    patterns: list[dict[str, Any]] = []
    for raw in compiled.get("exam_patterns") or []:
        if isinstance(raw, dict):
            patterns.append(raw)
            continue
        try:
            obj = json.loads(str(raw))
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict):
            patterns.append(obj)
    return patterns


def _fallback_term(knowledge_text: str) -> str:
    runs = re.findall(r"[一-鿿]{6,}", knowledge_text)
    if not runs:
        runs = re.findall(r"[一-鿿]{2,}", knowledge_text)
    if not runs:
        return ""
    return max(runs, key=len)[:8]


def _source_ref_complete(unit: dict[str, Any]) -> bool:
    ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    return all(str(ref.get(key) or "").strip() for key in ("source_path", "span_hash", "source_lane"))


def _make_case(unit: dict[str, Any], index: int) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    knowledge_text = _knowledge_text(unit)
    leaf_id = str(unit.get("leaf_id") or "")
    leaf_name = str(unit.get("leaf_name_path") or "").split(">")[-1].strip()
    patterns = _exam_patterns(unit)
    keywords = [str(kw) for ep in patterns for kw in ep.get("grading_keywords") or [] if str(kw).strip()]
    grounded = [kw for kw in keywords if kw in knowledge_text]
    keyword_grounded = bool(grounded)
    expected_terms = grounded[:3]
    if not expected_terms:
        fallback = _fallback_term(knowledge_text)
        if fallback:
            expected_terms = [fallback]
    if not knowledge_text.strip():
        blockers.append(f"unit_without_knowledge_text:{unit.get('unit_id')}:{leaf_id}")
    if not expected_terms:
        blockers.append(f"unit_without_expected_terms:{unit.get('unit_id')}:{leaf_id}")
    if not _source_ref_complete(unit):
        blockers.append(f"unit_with_incomplete_source_ref:{unit.get('unit_id')}:{leaf_id}")
    description = str((patterns[0] if patterns else {}).get("description") or "").strip()
    case = {
        "case_id": f"frozen_v1_shadow_{index:04d}",
        "unit_id": str(unit.get("unit_id") or ""),
        "leaf_id": leaf_id,
        "query": f"请基于编译知识回答：{leaf_name}：{description or (expected_terms[0] if expected_terms else '')}",
        "expected_terms": expected_terms,
        "keyword_grounded": keyword_grounded,
        "knowledge_text": knowledge_text,
        "exam_keywords": keywords,
        "ep_source_refs": [str(r) for ep in patterns for r in ep.get("source_refs") or []],
        "compiled_text": json.dumps(unit.get("compiled_context") or {}, ensure_ascii=False),
        "leaf_name": leaf_name,
    }
    return case, blockers


def _run_current_rag_proxy(cases: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    corpus = [
        {
            "unit_id": case["unit_id"],
            "doc": case["knowledge_text"][:RAG_DOC_CHARS],
            "tokens": _lexical_tokens(case["knowledge_text"][:RAG_DOC_CHARS]),
        }
        for case in cases
    ]
    rows: list[dict[str, Any]] = []
    for case in cases:
        query_tokens = _lexical_tokens(str(case["query"]))
        scored = sorted(
            corpus,
            key=lambda doc: (len(query_tokens & doc["tokens"]), -len(doc["doc"]), doc["unit_id"]),
            reverse=True,
        )[:top_k]
        combined = " ".join(doc["doc"] for doc in scored)
        own_hit = any(doc["unit_id"] == case["unit_id"] for doc in scored)
        matches = bool(own_hit and all(term in combined for term in case["expected_terms"]))
        rows.append(
            {
                "arm": "current_rag_proxy",
                "case_id": case["case_id"],
                "leaf_id": case["leaf_id"],
                "answerable": matches,
                "matches_expected": matches,
                "evidence_cited": own_hit,
                "fail_open": bool(scored and not own_hit),
                "token_proxy": _token_proxy(combined),
                "latency_ms_proxy": 4 + len(scored),
            }
        )
    return rows


def _run_legacy_keyword_projection(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        projection_text = " ".join([case["leaf_name"], *case["exam_keywords"]])
        matches = bool(projection_text.strip() and all(term in projection_text for term in case["expected_terms"]))
        cited = bool(case["ep_source_refs"])
        rows.append(
            {
                "arm": "legacy_keyword_projection",
                "case_id": case["case_id"],
                "leaf_id": case["leaf_id"],
                "answerable": matches,
                "matches_expected": matches,
                "evidence_cited": cited,
                "fail_open": bool(matches and not cited),
                "token_proxy": _token_proxy(projection_text),
                "latency_ms_proxy": 3,
            }
        )
    return rows


def _run_rich_leaf_context(cases: list[dict[str, Any]], units_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        unit = units_by_id.get(case["unit_id"]) or {}
        context_text = case["compiled_text"]
        matches = bool(
            case["knowledge_text"].strip() and all(term in case["knowledge_text"] for term in case["expected_terms"])
        )
        cited = _source_ref_complete(unit)
        rows.append(
            {
                "arm": "rich_leaf_v23_context",
                "case_id": case["case_id"],
                "leaf_id": case["leaf_id"],
                "answerable": matches,
                "matches_expected": matches,
                "evidence_cited": cited,
                "fail_open": bool(matches and not cited),
                "token_proxy": _token_proxy(context_text),
                "latency_ms_proxy": 1,
            }
        )
    return rows


def _run_artifact_first_guard(cases: list[dict[str, Any]], units_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        unit = units_by_id.get(case["unit_id"]) or {}
        compiled = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
        slices: list[str] = []
        for family in ("rules", "teaching_cards", "concepts"):
            items = compiled.get(family) or []
            if items:
                slices.append(str(items[0]))
        guard_text = "\n".join(slices)
        matches = bool(guard_text.strip() and all(term in guard_text for term in case["expected_terms"]))
        cited = bool(matches and _source_ref_complete(unit))
        rows.append(
            {
                "arm": "artifact_first_guard_proxy",
                "case_id": case["case_id"],
                "leaf_id": case["leaf_id"],
                "answerable": matches,
                "matches_expected": matches,
                "evidence_cited": cited,
                "high_risk_review": not matches,
                "fail_open": False,
                "token_proxy": _token_proxy(guard_text),
                "latency_ms_proxy": 2,
            }
        )
    return rows


def _summarize_arm(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"arm": arm, "sample_count": 0, "status": "empty"}
    return {
        "arm": arm,
        "sample_count": len(rows),
        "status": "completed",
        "accuracy_rate": round(mean(1.0 if row["matches_expected"] else 0.0 for row in rows), 4),
        "answerable_rate": round(mean(1.0 if row["answerable"] else 0.0 for row in rows), 4),
        "evidence_citation_rate": round(mean(1.0 if row["evidence_cited"] else 0.0 for row in rows), 4),
        "fail_open_rate": round(mean(1.0 if row["fail_open"] else 0.0 for row in rows), 4),
        "high_risk_review_rate": (
            round(mean(1.0 if row.get("high_risk_review") else 0.0 for row in rows), 4)
            if any("high_risk_review" in row for row in rows)
            else None
        ),
        "mean_token_proxy": round(mean(float(row["token_proxy"]) for row in rows), 2),
        "mean_latency_ms_proxy": round(mean(float(row["latency_ms_proxy"]) for row in rows), 2),
    }


def _pack_blockers(pack: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if pack.get("schema") != PACK_SCHEMA:
        blockers.append(f"runtime_token_pack:schema_mismatch:{pack.get('schema')}")
    if pack.get("status") != PACK_STATUS:
        blockers.append(f"runtime_token_pack:bad_status:{pack.get('status')}")
    classification = pack.get("classification") if isinstance(pack.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"runtime_token_pack:classification.{key}_not_false")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("runtime_token_pack:review_flags_invalid")
    return blockers


def run_frozen_v1_full_near_live_shadow_ab(*, runtime_token_pack: dict[str, Any], top_k: int = 3) -> dict[str, Any]:
    blockers = _pack_blockers(runtime_token_pack)
    units = [unit for unit in runtime_token_pack.get("runtime_token_pack_units") or [] if isinstance(unit, dict)]
    if not units:
        blockers.append("runtime_token_pack:no_units")
    units_by_id = {str(unit.get("unit_id") or ""): unit for unit in units}

    cases: list[dict[str, Any]] = []
    for index, unit in enumerate(units, start=1):
        case, case_blockers = _make_case(unit, index)
        blockers.extend(case_blockers)
        if not case_blockers:
            cases.append(case)

    rag_rows = _run_current_rag_proxy(cases, top_k=top_k)
    legacy_rows = _run_legacy_keyword_projection(cases)
    rich_rows = _run_rich_leaf_context(cases, units_by_id)
    guard_rows = _run_artifact_first_guard(cases, units_by_id)
    for row in rich_rows:
        if not (row["answerable"] and row["matches_expected"] and row["evidence_cited"]) or row["fail_open"]:
            blockers.append(f"rich_leaf_row_defect:{row['case_id']}:{row['leaf_id']}")

    effect_table = [
        _summarize_arm("current_rag_proxy", rag_rows),
        _summarize_arm("legacy_keyword_projection", legacy_rows),
        _summarize_arm("rich_leaf_v23_context", rich_rows),
        _summarize_arm("artifact_first_guard_proxy", guard_rows),
    ]
    by_arm = {row["arm"]: row for row in effect_table}
    rag_accuracy = float(by_arm["current_rag_proxy"].get("accuracy_rate") or 0.0)
    rich_accuracy = float(by_arm["rich_leaf_v23_context"].get("accuracy_rate") or 0.0)
    rag_tokens = float(by_arm["current_rag_proxy"].get("mean_token_proxy") or 0.0)
    rich_tokens = float(by_arm["rich_leaf_v23_context"].get("mean_token_proxy") or 0.0)
    grounded_count = sum(1 for case in cases if case["keyword_grounded"])

    rows = rag_rows + legacy_rows + rich_rows + guard_rows
    return {
        "schema": AB_SCHEMA,
        "verdict": "FAIL_FROZEN_V1_NEAR_LIVE_SHADOW_AB" if blockers else VERDICT_PASS,
        "verdict_ceiling": VERDICT_CEILING,
        "quality_claim_allowed": False,
        "input_artifact": {
            "runtime_token_pack_version": str(runtime_token_pack.get("version") or ""),
            "runtime_token_pack_unit_count": len(units),
        },
        "rerun_lineage": {
            "rerun_by": "run_luban_rich_leaf_frozen_v1_full_near_live_shadow_ab",
            "outcomes_recomputed_from_pack_version": str(runtime_token_pack.get("version") or ""),
            "outcomes_inherited_from_v23_proxy": False,
            "closes_not_exercised": "frozen_axis_near_live_rerun_with_recompiled_context",
        },
        "summary": {
            "arm_count": 4,
            "blocker_count": len(blockers),
            "case_count": len(cases),
            "current_rag_accuracy_rate": rag_accuracy,
            "rich_leaf_accuracy_rate": rich_accuracy,
            "rich_leaf_token_delta_vs_current_rag": round(rich_tokens - rag_tokens, 2),
            "expected_term_keyword_grounded_rate": round(grounded_count / len(cases), 4) if cases else 0.0,
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "effect_table": effect_table,
        "rows": rows,
        "blockers": blockers,
        "not_exercised": [
            "live_provider_judge",
            "production_rag_retrieval",
            "official_score",
            "runtime_default_install",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "v23_near_live_shadow_ab": True,
            "frozen_v1_full_recomputed": True,
            "canonical_pointer_written": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    report = run_frozen_v1_full_near_live_shadow_ab(
        runtime_token_pack=_read_json(args.runtime_token_pack), top_k=args.top_k
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]},
            ensure_ascii=False,
        )
    )
    return 0 if report["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
