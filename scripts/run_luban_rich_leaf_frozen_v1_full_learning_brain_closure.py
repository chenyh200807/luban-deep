#!/usr/bin/env python3
"""Frozen-v1 full-pack (v3.0, 1534 units) Learning Brain candidate closure.

Thin wrapper over ``build_v23_learning_brain_candidate_closure`` that:

1. Adapts the v3.0 frozen-full pack summary (``unit_count``) to the closure's
   ``leaf_scoped_runtime_unit_count`` contract (truthful: every v3.0 unit is
   leaf-scoped, one unit per evidence leaf).
2. Registers the frozen-v1 four-arm live provider A/B (100-leaf sample,
   commit 94a923cf6) and its residual work orders as the live evidence for
   this closure, with a mechanical consistency check against the recomputed
   near-live arms (conflict => live evidence must be re-shot, closure FAIL).
3. Reconciles the 23 v2.3 taxonomy gap candidates against the frozen axis
   ``-G`` leaves and the v3.0 runtime units, item by item, and resolves the
   ``canonical_taxonomy_extension_for_23_gaps`` not-exercised entry when all
   23 are accounted.

Review-only: no learner memory write, no canonical truth, no runtime install,
no provider calls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (  # noqa: E402
    build_v23_learning_brain_candidate_closure,
)
SCHEMA = "luban_rich_leaf_frozen_v1_full_learning_brain_closure.v1"
GO_EVIDENCE_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_go_evidence_20260613"
FULL_COMPILE_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613"
DEFAULT_RUNTIME_TOKEN_PACK = FULL_COMPILE_DIR / "runtime_token_pack_v30_frozen_full.json"
DEFAULT_NEAR_LIVE_AB = GO_EVIDENCE_DIR / "near_live_shadow_ab_v30_recomputed.json"
DEFAULT_BRIDGE = GO_EVIDENCE_DIR / "learning_evidence_candidate_bridge_v30.json"
DEFAULT_PROJECTION = GO_EVIDENCE_DIR / "pcp_nba_candidate_projection_v30.json"
DEFAULT_SANDBOX_GATE = GO_EVIDENCE_DIR / "test_learner_sandbox_readback_gate_v30.json"
DEFAULT_LIVE_AB = FULL_COMPILE_DIR / "frozen_v1_live_ab_sample100.json"
DEFAULT_LIVE_RESIDUAL_WORK_ORDERS = FULL_COMPILE_DIR / "frozen_v1_live_residual_work_orders.json"
DEFAULT_V23_RUNTIME_TOKEN_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v23_20260612/runtime_token_pack_v23.json"
)
DEFAULT_V2_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v2_20260612/runtime_token_pack_v2.json"
)
DEFAULT_TAXONOMY = REPO / "deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json"
DEFAULT_OUTPUT = GO_EVIDENCE_DIR / "learning_brain_candidate_closure_v30.json"

LIVE_AB_SCHEMA = "luban_rich_leaf_frozen_v1_live_ab.v1"
LIVE_AB_VERDICT = "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB"
RESIDUAL_SCHEMA = "luban_rich_leaf_frozen_v1_live_residual_work_orders.v1"
RESIDUAL_VERDICT = "PASS_FROZEN_V1_LIVE_RESIDUAL_WORK_ORDERS_READY"
GAP_CLASSIFICATION = "taxonomy_gap_extension_candidate"
GAP_MATCH_THRESHOLD = 25
NON_KNOWLEDGE_MARKER = "考情分析"
GAP_NOT_EXERCISED_KEY = "canonical_taxonomy_extension_for_23_gaps"
LIVE_NOT_EXERCISED_KEY = "live_provider_v23_four_arm_ab"
RESIDUAL_NOT_EXERCISED_KEY = "compiler_feedback_from_live_residuals"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _adapt_pack_summary(runtime_token_pack: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Map the v3.0 frozen-full summary onto the closure's unit-count contract."""
    blockers: list[str] = []
    summary = runtime_token_pack.get("summary") if isinstance(runtime_token_pack.get("summary"), dict) else {}
    unit_count = int(summary.get("unit_count") or 0)
    units = [u for u in runtime_token_pack.get("runtime_token_pack_units") or [] if isinstance(u, dict)]
    if unit_count != len(units):
        blockers.append(f"runtime_token_pack:summary_unit_count_mismatch:{unit_count}!={len(units)}")
    if int(summary.get("evidence_leaf_count") or 0) != unit_count:
        blockers.append("runtime_token_pack:units_not_leaf_scoped_one_to_one")
    if int(summary.get("unresolved_count") or 0) != 0:
        blockers.append(f"runtime_token_pack:unresolved_count_nonzero:{summary.get('unresolved_count')}")
    adapted = dict(runtime_token_pack)
    adapted["summary"] = {**summary, "leaf_scoped_runtime_unit_count": unit_count}
    return adapted, blockers


def _cjk_bigrams(text: str) -> set[str]:
    chars = re.findall(r"[一-鿿]", text)
    return {a + b for a, b in zip(chars, chars[1:])}


def _gap_items(v23_runtime_token_pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in v23_runtime_token_pack.get("non_runtime_accounted_items") or []
        if isinstance(item, dict) and item.get("classification") == GAP_CLASSIFICATION
    ]


def _gap_leaves(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    nodes_by_code = taxonomy.get("nodes_by_code") if isinstance(taxonomy.get("nodes_by_code"), dict) else {}
    return [
        node
        for code, node in nodes_by_code.items()
        if isinstance(node, dict) and re.search(r"-G\d+$", str(code))
    ]


def reconcile_taxonomy_gaps(
    *,
    v23_runtime_token_pack: dict[str, Any],
    v2_runtime_token_pack: dict[str, Any],
    taxonomy: dict[str, Any],
    runtime_token_pack: dict[str, Any],
) -> dict[str, Any]:
    gap_items = _gap_items(v23_runtime_token_pack)
    gap_leaves = _gap_leaves(taxonomy)
    runtime_leaf_ids = {
        str(unit.get("leaf_id") or "")
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict)
    }
    parent_units = {
        str(unit.get("unit_id") or ""): unit
        for unit in v2_runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict)
    }
    rows: list[dict[str, Any]] = []
    for item in gap_items:
        parent = parent_units.get(str(item.get("parent_unit_id") or ""))
        parent_text = json.dumps(parent.get("compiled_context") or {}, ensure_ascii=False)[:4000] if parent else ""
        item_text = " ".join(
            [str(item.get("unresolved_reason") or ""), str(item.get("suggested_gap_family") or ""), parent_text]
        )
        item_bigrams = _cjk_bigrams(item_text)
        best: tuple[int, int, str, str] | None = None
        for node in gap_leaves:
            keywords = [str(kw) for kw in node.get("keywords") or [] if str(kw).strip()]
            keyword_hits = sum(1 for kw in keywords if kw in item_text)
            overlap = len(item_bigrams & _cjk_bigrams(str(node.get("name") or "") + " " + " ".join(keywords)))
            score = keyword_hits * 10 + overlap
            key = (score, keyword_hits, str(node.get("code") or ""), str(node.get("name") or ""))
            if best is None or key[:2] > best[:2] or (key[:2] == best[:2] and key[2] < best[2]):
                best = key
        score, keyword_hits, leaf_code, leaf_name = best or (0, 0, "", "")
        non_knowledge = NON_KNOWLEDGE_MARKER in str(item.get("unresolved_reason") or "")
        matched = score >= GAP_MATCH_THRESHOLD
        if matched:
            resolution = "matched_to_frozen_axis_gap_leaf"
        elif non_knowledge:
            resolution = "non_knowledge_adjudicated_no_leaf_minted"
        else:
            resolution = "unresolved"
        rows.append(
            {
                "item_id": str(item.get("item_id") or ""),
                "parent_unit_id": str(item.get("parent_unit_id") or ""),
                "unresolved_reason": str(item.get("unresolved_reason") or "")[:120],
                "matched_gap_leaf_id": leaf_code if matched else None,
                "matched_gap_leaf_name": leaf_name if matched else None,
                "match_score": score,
                "match_keyword_hits": keyword_hits,
                "matched_leaf_in_frozen_axis": matched,
                "matched_leaf_in_v30_runtime": bool(matched and leaf_code in runtime_leaf_ids),
                "resolution": resolution,
            }
        )
    resolved_in_runtime = [row for row in rows if row["resolution"] == "matched_to_frozen_axis_gap_leaf"]
    adjudicated = [row for row in rows if row["resolution"] == "non_knowledge_adjudicated_no_leaf_minted"]
    unresolved = [
        row
        for row in rows
        if row["resolution"] == "unresolved"
        or (row["resolution"] == "matched_to_frozen_axis_gap_leaf" and not row["matched_leaf_in_v30_runtime"])
    ]
    runtime_gap_leaf_ids = sorted(leaf for leaf in runtime_leaf_ids if re.search(r"-G\d+$", leaf))
    return {
        "gap_item_count": len(rows),
        "matched_in_frozen_axis_and_v30_runtime_count": len(
            [row for row in resolved_in_runtime if row["matched_leaf_in_v30_runtime"]]
        ),
        "non_knowledge_adjudicated_count": len(adjudicated),
        "unresolved_count": len(unresolved),
        "all_gaps_accounted": bool(rows) and not unresolved,
        "frozen_axis_gap_leaf_count": len(gap_leaves),
        "v30_runtime_gap_leaf_count": len(runtime_gap_leaf_ids),
        "v30_runtime_gap_leaf_ids": runtime_gap_leaf_ids,
        "adjudication_basis": "taxonomy freeze v1 (commit 113de99c0): 招投标考情分析 = non-knowledge teaching meta, no leaf minted",
        "rows": rows,
    }


def _live_ab_blockers(live_ab: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if live_ab.get("schema") != LIVE_AB_SCHEMA:
        blockers.append(f"live_ab:schema_mismatch:{live_ab.get('schema')}")
    if live_ab.get("verdict") != LIVE_AB_VERDICT:
        blockers.append(f"live_ab:bad_verdict:{live_ab.get('verdict')}")
    if live_ab.get("quality_claim_allowed") is not False:
        blockers.append("live_ab:quality_claim_allowed")
    classification = live_ab.get("classification") if isinstance(live_ab.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"live_ab:classification.{key}_not_false")
    safety = live_ab.get("safety") if isinstance(live_ab.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"live_ab:safety.{key}_not_false")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append("live_ab:safety.production_write_count_nonzero")
    return blockers


def _arm_accuracy(report: dict[str, Any], *, arm_key: str, arm_name: str) -> float | None:
    for arm in report.get(arm_key) or []:
        if isinstance(arm, dict) and arm.get("arm") == arm_name:
            value = arm.get("accuracy_rate")
            return float(value) if value is not None else None
    return None


def check_live_evidence_consistency(*, near_live_ab: dict[str, Any], live_ab: dict[str, Any]) -> dict[str, Any]:
    near_rich = _arm_accuracy(near_live_ab, arm_key="effect_table", arm_name="rich_leaf_v23_context")
    near_rag = _arm_accuracy(near_live_ab, arm_key="effect_table", arm_name="current_rag_proxy")
    live_rich = _arm_accuracy(live_ab, arm_key="arms", arm_name="rich_leaf_context_live")
    live_rag = _arm_accuracy(live_ab, arm_key="arms", arm_name="current_rag_projection_live")
    comparable = None not in (near_rich, near_rag, live_rich, live_rag)
    near_delta = round(near_rich - near_rag, 4) if comparable else None
    live_delta = round(live_rich - live_rag, 4) if comparable else None
    conflict = (not comparable) or (near_delta <= 0) != (live_delta <= 0)
    return {
        "comparable": bool(comparable),
        "near_live_rich_accuracy": near_rich,
        "near_live_rag_accuracy": near_rag,
        "live_rich_accuracy": live_rich,
        "live_rag_accuracy": live_rag,
        "near_live_rich_minus_rag": near_delta,
        "live_rich_minus_rag": live_delta,
        "conflict": bool(conflict),
        "reuse_policy": (
            "live AB sample100 (seed=%s) reused as v3.0 live evidence; no re-shoot needed"
            % live_ab.get("sample_seed")
            if not conflict
            else "conflict detected: re-shoot up to +50 leaves x 4 arms required"
        ),
    }


def build_frozen_v1_full_learning_brain_closure(
    *,
    runtime_token_pack: dict[str, Any],
    near_live_ab: dict[str, Any],
    bridge: dict[str, Any],
    projection: dict[str, Any],
    sandbox_gate: dict[str, Any],
    live_ab: dict[str, Any],
    live_residual_work_orders: dict[str, Any],
    v23_runtime_token_pack: dict[str, Any],
    v2_runtime_token_pack: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    adapted_pack, blockers = _adapt_pack_summary(runtime_token_pack)
    base = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=adapted_pack,
        near_live_ab=near_live_ab,
        bridge=bridge,
        projection=projection,
        sandbox_gate=sandbox_gate,
        live_provider_ab=None,
        live_residual_work_orders=None,
    )
    blockers.extend(base.get("blockers") or [])

    rerun_lineage = near_live_ab.get("rerun_lineage") if isinstance(near_live_ab.get("rerun_lineage"), dict) else {}
    if rerun_lineage.get("outcomes_inherited_from_v23_proxy") is not False:
        blockers.append("near_live_ab:outcomes_not_recomputed_from_v30_context")

    blockers.extend(_live_ab_blockers(live_ab))
    if live_residual_work_orders.get("schema") != RESIDUAL_SCHEMA:
        blockers.append(f"live_residual_work_orders:schema_mismatch:{live_residual_work_orders.get('schema')}")
    if live_residual_work_orders.get("verdict") != RESIDUAL_VERDICT:
        blockers.append(f"live_residual_work_orders:bad_verdict:{live_residual_work_orders.get('verdict')}")

    consistency = check_live_evidence_consistency(near_live_ab=near_live_ab, live_ab=live_ab)
    if consistency["conflict"]:
        blockers.append("live_evidence_conflict_with_near_live_rerun:reshoot_required")

    gap_reconciliation = reconcile_taxonomy_gaps(
        v23_runtime_token_pack=v23_runtime_token_pack,
        v2_runtime_token_pack=v2_runtime_token_pack,
        taxonomy=taxonomy,
        runtime_token_pack=runtime_token_pack,
    )

    not_exercised = [item for item in base.get("not_exercised") or []]
    resolved_not_exercised: list[dict[str, Any]] = []
    if gap_reconciliation["all_gaps_accounted"] and GAP_NOT_EXERCISED_KEY in not_exercised:
        not_exercised.remove(GAP_NOT_EXERCISED_KEY)
        resolved_not_exercised.append(
            {
                "key": GAP_NOT_EXERCISED_KEY,
                "resolved_by": "taxonomy_freeze_v1_gap_fold + v3.0 frozen full compile",
                "evidence": "gap_reconciliation",
            }
        )
    if not _live_ab_blockers(live_ab) and not consistency["conflict"] and LIVE_NOT_EXERCISED_KEY in not_exercised:
        not_exercised.remove(LIVE_NOT_EXERCISED_KEY)
        resolved_not_exercised.append(
            {
                "key": LIVE_NOT_EXERCISED_KEY,
                "resolved_by": "frozen_v1_live_ab_sample100 (commit 94a923cf6, seed=%s) registered as v3.0 live evidence"
                % live_ab.get("sample_seed"),
                "evidence": "registered_live_evidence",
            }
        )
    if live_residual_work_orders.get("verdict") == RESIDUAL_VERDICT and RESIDUAL_NOT_EXERCISED_KEY in not_exercised:
        not_exercised.remove(RESIDUAL_NOT_EXERCISED_KEY)
        resolved_not_exercised.append(
            {
                "key": RESIDUAL_NOT_EXERCISED_KEY,
                "resolved_by": "frozen_v1_live_residual_work_orders (17 work orders) registered",
                "evidence": "registered_live_evidence",
            }
        )

    summary = dict(base.get("summary") or {})
    for legacy_key in ("original_v2_source_file_units", "original_units_accounted", "non_runtime_excluded_or_gap", "taxonomy_gap_candidates"):
        summary.pop(legacy_key, None)
    pack_summary = runtime_token_pack.get("summary") if isinstance(runtime_token_pack.get("summary"), dict) else {}
    live_summary = live_ab.get("summary") if isinstance(live_ab.get("summary"), dict) else {}
    residual_summary = (
        live_residual_work_orders.get("summary") if isinstance(live_residual_work_orders.get("summary"), dict) else {}
    )
    summary.update(
        {
            "frozen_v1_unit_count": int(pack_summary.get("unit_count") or 0),
            "frozen_v1_evidence_leaf_count": int(pack_summary.get("evidence_leaf_count") or 0),
            "frozen_v1_gap_leaf_unit_count": gap_reconciliation["v30_runtime_gap_leaf_count"],
            "gap_items_reconciled": gap_reconciliation["gap_item_count"],
            "gap_items_matched_in_v30_runtime": gap_reconciliation["matched_in_frozen_axis_and_v30_runtime_count"],
            "gap_items_non_knowledge_adjudicated": gap_reconciliation["non_knowledge_adjudicated_count"],
            "gap_items_unresolved": gap_reconciliation["unresolved_count"],
            "live_provider_sample_count": int(live_summary.get("sample_count") or 0),
            "live_provider_call_count": int(live_summary.get("provider_call_count") or 0),
            "live_provider_total_tokens": int(live_summary.get("total_tokens") or 0),
            "live_residual_work_order_count": int(residual_summary.get("work_order_count") or 0),
            "blocker_count": len(blockers),
        }
    )

    decision_table = [row for row in base.get("decision_table") or []]
    for row in decision_table:
        if row.get("gate") == "v2.3 projected live provider A/B":
            row["gate"] = "frozen v1 four-arm live provider A/B (registered)"
            row["verdict"] = "PASS" if not consistency["conflict"] else "FAIL"
            row["evidence"] = "frozen_v1_live_ab_sample100 (94a923cf6)"
        if row.get("gate") == "compiler feedback residual work orders":
            row["verdict"] = "PASS"
            row["evidence"] = "frozen_v1_live_residual_work_orders"
    decision_table.append(
        {
            "gate": "canonical taxonomy extension for 23 gaps",
            "verdict": "PASS" if gap_reconciliation["all_gaps_accounted"] else "FAIL",
            "evidence": "gap_reconciliation (taxonomy-frozen-v1-20260612 + v3.0 runtime units)",
        }
    )

    verdict = (
        "FAIL_SAFETY_OR_CONTRACT"
        if blockers
        else "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
    )
    return {
        **base,
        "schema": SCHEMA,
        "base_schema": base.get("schema"),
        "verdict": verdict,
        "summary": summary,
        "decision_table": decision_table,
        "blockers": blockers,
        "not_exercised": not_exercised,
        "resolved_not_exercised": resolved_not_exercised,
        "gap_reconciliation": gap_reconciliation,
        "live_evidence_consistency": consistency,
        "registered_live_evidence": {
            "live_ab_schema": live_ab.get("schema"),
            "live_ab_verdict": live_ab.get("verdict"),
            "live_ab_sample_seed": live_ab.get("sample_seed"),
            "live_ab_commit": "94a923cf6",
            "live_residual_work_orders_verdict": live_residual_work_orders.get("verdict"),
        },
        "classification": {
            **(base.get("classification") or {}),
            "frozen_v1_full_learning_brain_closure": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--near-live-ab", type=Path, default=DEFAULT_NEAR_LIVE_AB)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--projection", type=Path, default=DEFAULT_PROJECTION)
    parser.add_argument("--sandbox-gate", type=Path, default=DEFAULT_SANDBOX_GATE)
    parser.add_argument("--live-ab", type=Path, default=DEFAULT_LIVE_AB)
    parser.add_argument("--live-residual-work-orders", type=Path, default=DEFAULT_LIVE_RESIDUAL_WORK_ORDERS)
    parser.add_argument("--v23-runtime-token-pack", type=Path, default=DEFAULT_V23_RUNTIME_TOKEN_PACK)
    parser.add_argument("--v2-runtime-token-pack", type=Path, default=DEFAULT_V2_RUNTIME_TOKEN_PACK)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_frozen_v1_full_learning_brain_closure(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        near_live_ab=_read_json(args.near_live_ab),
        bridge=_read_json(args.bridge),
        projection=_read_json(args.projection),
        sandbox_gate=_read_json(args.sandbox_gate),
        live_ab=_read_json(args.live_ab),
        live_residual_work_orders=_read_json(args.live_residual_work_orders),
        v23_runtime_token_pack=_read_json(args.v23_runtime_token_pack),
        v2_runtime_token_pack=_read_json(args.v2_runtime_token_pack),
        taxonomy=_read_json(args.taxonomy),
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "verdict": report["verdict"],
                "summary": report["summary"],
                "not_exercised": report["not_exercised"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
