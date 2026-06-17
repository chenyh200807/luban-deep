#!/usr/bin/env python3
"""Materialize v2.3 live-provider residuals into compiler work orders."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_v23_live_residual_work_orders.v1"
LIVE_SCHEMA = "luban_rich_leaf_v23_live_provider_shadow_ab.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
DEFAULT_LIVE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_provider_shadow_ab_20260612/v23_live_provider_shadow_ab_sample8_deepseek_promptfix.json"
)
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v23_20260612/runtime_token_pack_v23.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_residual_work_orders_20260612/live_residual_work_orders_sample8.json"
)


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


def _units_by_id(runtime_token_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(unit.get("unit_id")): unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }


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
    if unit.get("review_source") == "ai_shadow_review":
        reasons.add("ai_shadow_review_needs_human_or_council_recheck")
    if unit.get("review_source") == "deterministic_dedup_margin":
        reasons.add("deterministic_linker_false_positive_candidate")
    return sorted(reasons)


def build_v23_live_residual_work_orders(
    *,
    live_provider_ab: dict[str, Any],
    runtime_token_pack: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if live_provider_ab.get("schema") != LIVE_SCHEMA:
        blockers.append(f"live_ab_schema_mismatch:{live_provider_ab.get('schema')}")
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if live_provider_ab.get("verdict") != "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB":
        blockers.append(f"live_ab_not_pass:{live_provider_ab.get('verdict')}")
    blockers.extend(_safety_blockers("live_ab", live_provider_ab))
    blockers.extend(_safety_blockers("runtime_token_pack", runtime_token_pack))

    units = _units_by_id(runtime_token_pack)
    failed_by_unit: dict[str, list[dict[str, Any]]] = {}
    for row in live_provider_ab.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "completed" or row.get("matches_expected") is not False:
            continue
        if row.get("expected_answerable") is not True or row.get("answerable") is not False:
            continue
        arm = str(row.get("arm") or "")
        if arm not in {"legacy_keyword_projection_live", "rich_leaf_v23_context_live", "artifact_first_guard_live"}:
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
                "work_order_id": _stable_id("v23_live_residual_work_order", payload),
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
                "recommended_action": "re-run source evidence search and taxonomy leaf linking for this unit before runtime promotion",
            }
        )

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "live_provider_ab": live_provider_ab.get("schema"),
            "runtime_token_pack": runtime_token_pack.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS_LIVE_RESIDUAL_WORK_ORDERS_READY",
        "quality_claim_allowed": False,
        "summary": {
            "live_sample_count": int((live_provider_ab.get("summary") or {}).get("sample_count") or 0),
            "failed_runtime_unit_count": len(work_orders),
            "work_order_count": len(work_orders),
            "blocker_count": len(blockers),
            "production_write_count": 0,
        },
        "work_orders": work_orders,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "v23_live_residual_work_orders": True,
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
    parser.add_argument("--live-provider-ab", type=Path, default=DEFAULT_LIVE_AB)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_v23_live_residual_work_orders(
        live_provider_ab=_read_json(args.live_provider_ab),
        runtime_token_pack=_read_json(args.runtime_token_pack),
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
