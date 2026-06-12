#!/usr/bin/env python3
"""Materialize frozen-v1 live A/B residuals into typed compiler work orders.

A residual is a sampled leaf whose context arm completed but rejected a leaf
that carries real evidence (expected_answerable=true, answerable=false).
Each residual leaf gets a typed work order (demotion shape reused from the
v2.3 live residual flow) and is flagged quarantine_candidate in an annotated
copy of the full pack. Candidate/review tier only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_rich_leaf_frozen_v1_live_residual_work_orders.v1"
LIVE_SCHEMA = "luban_rich_leaf_frozen_v1_live_ab.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
ANNOTATED_VERSION = "v3.0.1_frozen_v1_quarantine_annotated"
CONTEXT_ARMS = {
    "legacy_keyword_projection_live",
    "rich_leaf_context_live",
    "artifact_first_guard_live",
}

DEFAULT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613"
DEFAULT_LIVE_AB = DEFAULT_DIR / "frozen_v1_live_ab_sample100.json"
DEFAULT_RUNTIME_TOKEN_PACK = DEFAULT_DIR / "runtime_token_pack_v30_frozen_full.json"
DEFAULT_OUTPUT = DEFAULT_DIR / "frozen_v1_live_residual_work_orders.json"
DEFAULT_OUTPUT_PACK = DEFAULT_DIR / "runtime_token_pack_v301_quarantine_annotated.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _safety_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("candidate_only", "review_only"):
        if classification.get(key) is not True:
            blockers.append(f"{name}:{key}_not_true")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{name}:{key}_not_false")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append(f"{name}:production_write_count_nonzero")
    if safety.get("release_truth_claimed") is not False:
        blockers.append(f"{name}:release_truth_claimed_not_false")
    return blockers


def _reason_codes(rows: list[dict[str, Any]], unit: dict[str, Any]) -> list[str]:
    reasons = {"live_provider_expected_answerable_but_context_rejected"}
    answer_text = " ".join(str(row.get("answer_text") or "") for row in rows)
    leaf_name = str(unit.get("leaf_name_path") or "")
    context_text = json.dumps(unit.get("compiled_context") or {}, ensure_ascii=False)
    leaf_terms = [part.strip() for part in leaf_name.replace(">", " ").split() if len(part.strip()) >= 2]
    if answer_text and any(marker in answer_text for marker in ("未涉及", "未提供", "无相关", "无法回答")):
        reasons.add("provider_reported_missing_relevant_evidence")
    if leaf_terms and not any(term in context_text for term in leaf_terms[-2:]):
        reasons.add("leaf_context_keyword_mismatch")
    if unit.get("review_source") == "frozen_v1_base_pack_carryover":
        reasons.add("base_pack_carryover_needs_recompile")
    return sorted(reasons)


def build_frozen_v1_live_residual_work_orders(
    *,
    live_ab: dict[str, Any],
    runtime_token_pack: dict[str, Any],
    annotated_version: str = ANNOTATED_VERSION,
) -> dict[str, Any]:
    blockers: list[str] = []
    if live_ab.get("schema") != LIVE_SCHEMA:
        blockers.append(f"live_ab_schema_mismatch:{live_ab.get('schema')}")
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if live_ab.get("verdict") != "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB":
        blockers.append(f"live_ab_not_pass:{live_ab.get('verdict')}")
    blockers.extend(_safety_blockers("live_ab", live_ab))
    blockers.extend(_safety_blockers("runtime_token_pack", runtime_token_pack))

    units = {
        str(unit.get("unit_id")): unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }

    failed_by_unit: dict[str, list[dict[str, Any]]] = {}
    provider_error_rows: list[dict[str, Any]] = []
    for row in live_ab.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") == "failed":
            provider_error_rows.append(
                {"unit_id": row.get("unit_id"), "arm": row.get("arm"), "error": row.get("error")}
            )
            continue
        if row.get("status") != "completed" or row.get("matches_expected") is not False:
            continue
        if row.get("expected_answerable") is not True or row.get("answerable") is not False:
            continue
        if str(row.get("arm") or "") not in CONTEXT_ARMS:
            continue
        unit_id = str(row.get("unit_id") or "")
        if unit_id:
            failed_by_unit.setdefault(unit_id, []).append(row)

    work_orders: list[dict[str, Any]] = []
    for unit_id, rows in sorted(failed_by_unit.items()):
        unit = units.get(unit_id)
        if not unit:
            blockers.append(f"failed_row_missing_runtime_unit:{unit_id}")
            continue
        source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
        payload = {
            "unit_id": unit_id,
            "leaf_id": unit.get("leaf_id"),
            "failed_arms": sorted({str(row.get("arm") or "") for row in rows}),
        }
        work_orders.append(
            {
                "work_order_id": _stable_id("frozen_v1_live_residual_work_order", payload),
                "work_order_type": "compiler_feedback_source_or_leaf_recheck",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "leaf_id": unit.get("leaf_id"),
                "leaf_name_path": unit.get("leaf_name_path"),
                "unit_id": unit_id,
                "source_ref": source_ref,
                "failed_arms": payload["failed_arms"],
                "reason_codes": _reason_codes(rows, unit),
                "provider_residuals": [
                    {
                        "case_id": row.get("case_id"),
                        "arm": row.get("arm"),
                        "answer_text": row.get("answer_text"),
                        "expected_answerable": row.get("expected_answerable"),
                        "answerable": row.get("answerable"),
                    }
                    for row in rows
                ],
                "recommended_action": "re-run source evidence search and frozen-axis leaf compile for this unit before runtime promotion",
            }
        )

    quarantine_ids = sorted(
        {str(order["unit_id"]) for order in work_orders if order.get("unit_id") in units}
    )
    work_order_by_unit = {str(order["unit_id"]): str(order["work_order_id"]) for order in work_orders}
    annotated_pack: dict[str, Any] | None = None
    if not blockers:
        annotated_units = [
            (
                {
                    **unit,
                    "quarantine_candidate": True,
                    "quarantine_work_order_id": work_order_by_unit[str(unit.get("unit_id"))],
                }
                if str(unit.get("unit_id")) in work_order_by_unit
                else unit
            )
            for unit in runtime_token_pack.get("runtime_token_pack_units") or []
            if isinstance(unit, dict)
        ]
        annotated_pack = {
            **runtime_token_pack,
            "version": annotated_version,
            "runtime_token_pack_units": annotated_units,
            "quarantine": {
                "quarantine_candidate_unit_ids": quarantine_ids,
                "quarantine_candidate_count": len(quarantine_ids),
                "source_live_ab_schema": LIVE_SCHEMA,
            },
            "patch_lineage": {
                "base_version": runtime_token_pack.get("version"),
                "annotation_schema": SCHEMA,
                "quarantine_candidate_unit_ids": quarantine_ids,
            },
        }

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "live_ab": live_ab.get("schema"),
            "runtime_token_pack": runtime_token_pack.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS_FROZEN_V1_LIVE_RESIDUAL_WORK_ORDERS_READY",
        "quality_claim_allowed": False,
        "summary": {
            "live_sample_count": int((live_ab.get("summary") or {}).get("sample_count") or 0),
            "failed_runtime_unit_count": len(work_orders),
            "work_order_count": len(work_orders),
            "quarantine_candidate_count": len(quarantine_ids),
            "provider_error_row_count": len(provider_error_rows),
            "blocker_count": len(blockers),
            "production_write_count": 0,
        },
        "work_orders": work_orders,
        "provider_error_rows": provider_error_rows,
        "annotated_runtime_token_pack": annotated_pack,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "frozen_v1_live_residual_work_orders": True,
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
    parser.add_argument("--live-ab", type=Path, default=DEFAULT_LIVE_AB)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-pack", type=Path, default=DEFAULT_OUTPUT_PACK)
    parser.add_argument("--annotated-version", default=ANNOTATED_VERSION)
    args = parser.parse_args(argv)

    report = build_frozen_v1_live_residual_work_orders(
        live_ab=_read_json(args.live_ab),
        runtime_token_pack=_read_json(args.runtime_token_pack),
        annotated_version=args.annotated_version,
    )
    annotated_pack = report.pop("annotated_runtime_token_pack", None)
    report["annotated_runtime_token_pack_path"] = str(args.output_pack) if annotated_pack else None
    _write_json(args.output, report)
    if annotated_pack is not None:
        _write_json(args.output_pack, annotated_pack)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_pack": str(args.output_pack) if annotated_pack else None,
                "verdict": report["verdict"],
                "summary": report["summary"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
