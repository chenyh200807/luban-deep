#!/usr/bin/env python3
"""Run a v2.3 RuntimeTokenPack live-provider shadow A/B.

This is a projected live-provider trace: it calls a real provider, but it does
not call production RAG, install runtime defaults, or write canonical truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import (
    PROVIDER_DEFAULTS,
    _openai_compat_provider,
    _parse_json_object,
)


SCHEMA = "luban_rich_leaf_v23_live_provider_shadow_ab.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
NEAR_LIVE_SCHEMA = "luban_rich_leaf_v23_near_live_shadow_ab.v1"
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v23_20260612/runtime_token_pack_v23.json"
)
DEFAULT_NEAR_LIVE_AB = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_near_live_shadow_ab_20260612/v23_near_live_shadow_ab.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_provider_shadow_ab_20260612/v23_live_provider_shadow_ab_sample.json"
)
ARMS = (
    "current_rag_projection_live",
    "legacy_keyword_projection_live",
    "rich_leaf_v23_context_live",
    "artifact_first_guard_live",
)


ProviderCall = Callable[..., dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safety_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("candidate_only") is not True:
        blockers.append(f"{name}:candidate_only_not_true")
    if classification.get("review_only") is not True:
        blockers.append(f"{name}:review_only_not_true")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{name}:{key}_not_false")
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"{name}:safety.{key}_not_false")
    if int(safety.get("production_write_count") or 0) != 0:
        blockers.append(f"{name}:production_write_count_nonzero")
    return blockers


def _rows_by_arm(near_live_ab: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row.get("case_id") or ""), str(row.get("arm") or "")): row
        for row in near_live_ab.get("rows") or []
        if isinstance(row, dict) and row.get("case_id") and row.get("arm")
    }


def _units_by_leaf(runtime_token_pack: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_leaf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in runtime_token_pack.get("runtime_token_pack_units") or []:
        if isinstance(unit, dict) and unit.get("leaf_id") and unit.get("unit_id"):
            by_leaf[str(unit["leaf_id"])].append(unit)
    return by_leaf


def _select_cases(
    *,
    runtime_token_pack: dict[str, Any],
    near_live_ab: dict[str, Any],
    sample_limit: int,
    start_index: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    row_index = _rows_by_arm(near_live_ab)
    rich_rows = [
        row
        for row in near_live_ab.get("rows") or []
        if isinstance(row, dict) and row.get("arm") == "rich_leaf_v23_context"
    ]
    units_by_leaf = _units_by_leaf(runtime_token_pack)
    offsets: dict[str, int] = defaultdict(int)
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in rich_rows:
        leaf_id = str(row.get("leaf_id") or "")
        units = units_by_leaf.get(leaf_id) or []
        offset = offsets[leaf_id]
        unit = units[offset] if offset < len(units) else (units[-1] if units else None)
        offsets[leaf_id] += 1
        if unit is None:
            continue
        case_id = str(row.get("case_id") or "")
        if not all((case_id, arm) in row_index for arm in ("current_rag_proxy", "legacy_keyword_projection", "artifact_first_guard_proxy")):
            continue
        selected.append((row, unit))
    return selected[max(0, start_index) : max(0, start_index) + max(0, sample_limit)]


def _compact_context(compiled_context: dict[str, Any], *, max_items_per_family: int) -> dict[str, list[str]]:
    compact: dict[str, list[str]] = {}
    for family in ("concepts", "definitions", "rules", "procedures", "numeric_constraints", "exam_patterns", "teaching_cards"):
        values = [str(item) for item in compiled_context.get(family) or [] if str(item).strip()]
        if values:
            compact[family] = values[:max_items_per_family]
    return compact


def _arm_context(arm: str, *, proxy_row: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    source_pointer = {
        "source_lane": source_ref.get("source_lane"),
        "source_path": source_ref.get("source_path"),
        "record_id": source_ref.get("record_id"),
        "span_hash": source_ref.get("span_hash"),
    }
    if arm == "current_rag_projection_live":
        return {
            "mode": arm,
            "retrieved_evidence": [source_pointer] if proxy_row.get("answerable") else [],
            "retrieval_projection": "current_rag_proxy_not_production_rag",
        }
    if arm == "legacy_keyword_projection_live":
        return {
            "mode": arm,
            "leaf_name_path": unit.get("leaf_name_path"),
            "keywords": _compact_context(compiled_context, max_items_per_family=1) if proxy_row.get("answerable") else {},
            "retrieval_projection": "legacy_keyword_projection_not_production_runtime",
        }
    if arm == "artifact_first_guard_live":
        return {
            "mode": arm,
            "leaf_id": unit.get("leaf_id"),
            "source_ref": source_pointer,
            "guardrails": [
                "only_answer_if_source_ref_present",
                "do_not_invent_evidence",
                "fail_closed_if_context_insufficient",
            ],
            "compiled_context": _compact_context(compiled_context, max_items_per_family=1),
        }
    return {
        "mode": arm,
        "leaf_id": unit.get("leaf_id"),
        "leaf_name_path": unit.get("leaf_name_path"),
        "source_ref": source_pointer,
        "compiled_context": _compact_context(compiled_context, max_items_per_family=2),
    }


def _messages(arm: str, *, case_id: str, proxy_row: dict[str, Any], unit: dict[str, Any]) -> list[dict[str, str]]:
    leaf_name = str(unit.get("leaf_name_path") or unit.get("leaf_id") or "该知识点")
    payload = {
        "case_id": case_id,
        "arm": arm,
        "question": f"请用给定证据概述「{leaf_name}」的核心定义、规则或考试要点。",
        "task": "Decide whether the provided context is sufficient to answer this concrete construction-exam knowledge question.",
        "context": _arm_context(arm, proxy_row=proxy_row, unit=unit),
        "required_json": {
            "answerable": "boolean",
            "evidence_cited": "boolean",
            "fail_open": "boolean",
            "answer": "short Chinese string",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict source-grounded shadow evaluator. Return one JSON object only. "
                "If the context lacks source evidence, answerable=false and fail_open=false. "
                "Never invent source evidence."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    return {
        "arm": arm,
        "status": "completed" if rows and len(completed) == len(rows) else "failed",
        "sample_count": len(rows),
        "provider_call_count": len(completed),
        "accuracy_rate": round(mean([1.0 if row.get("matches_expected") else 0.0 for row in completed]), 4) if completed else 0.0,
        "answerable_rate": round(mean([1.0 if row.get("answerable") else 0.0 for row in completed]), 4) if completed else 0.0,
        "evidence_citation_rate": round(mean([1.0 if row.get("evidence_cited") else 0.0 for row in completed]), 4) if completed else 0.0,
        "fail_open_rate": round(mean([1.0 if row.get("fail_open") else 0.0 for row in completed]), 4) if completed else 0.0,
        "mean_prompt_tokens": round(mean([int(row.get("prompt_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_completion_tokens": round(mean([int(row.get("completion_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_total_tokens": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
    }


def build_v23_live_provider_shadow_ab(
    *,
    runtime_token_pack: dict[str, Any],
    near_live_ab: dict[str, Any],
    sample_limit: int,
    provider_call: ProviderCall | None,
    model: str,
    start_index: int = 0,
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if near_live_ab.get("schema") != NEAR_LIVE_SCHEMA:
        blockers.append(f"near_live_schema_mismatch:{near_live_ab.get('schema')}")
    if runtime_token_pack.get("status") != "candidate_ready_for_shadow_ab_full_accounted":
        blockers.append(f"runtime_token_pack_status_invalid:{runtime_token_pack.get('status')}")
    if near_live_ab.get("verdict") != "PASS_V23_NEAR_LIVE_SHADOW_AB":
        blockers.append(f"near_live_verdict_invalid:{near_live_ab.get('verdict')}")
    blockers.extend(_safety_blockers("runtime_token_pack", runtime_token_pack))
    blockers.extend(_safety_blockers("near_live_ab", near_live_ab))
    if provider_call is None:
        blockers.append("provider_call_not_configured")

    selected = _select_cases(
        runtime_token_pack=runtime_token_pack,
        near_live_ab=near_live_ab,
        sample_limit=sample_limit,
        start_index=start_index,
    )
    if not selected:
        blockers.append("no_v23_cases_selected")

    row_index = _rows_by_arm(near_live_ab)
    rows: list[dict[str, Any]] = []
    prompt_tokens = 0
    completion_tokens = 0
    if not blockers and provider_call is not None:
        for rich_row, unit in selected:
            case_id = str(rich_row.get("case_id") or "")
            proxy_rows = {
                "current_rag_projection_live": row_index[(case_id, "current_rag_proxy")],
                "legacy_keyword_projection_live": row_index[(case_id, "legacy_keyword_projection")],
                "rich_leaf_v23_context_live": rich_row,
                "artifact_first_guard_live": row_index[(case_id, "artifact_first_guard_proxy")],
            }
            for arm in ARMS:
                proxy_row = proxy_rows[arm]
                expected_answerable = bool(proxy_row.get("answerable"))
                messages = _messages(arm, case_id=case_id, proxy_row=proxy_row, unit=unit)
                try:
                    response = provider_call(model, messages, timeout_s=timeout_s)
                    parsed = _parse_json_object(str(response.get("content") or ""))
                    answerable = bool(parsed.get("answerable"))
                    evidence_cited = bool(parsed.get("evidence_cited"))
                    fail_open = bool(parsed.get("fail_open"))
                    p_tokens = int(response.get("prompt_tokens") or 0)
                    c_tokens = int(response.get("completion_tokens") or 0)
                    prompt_tokens += p_tokens
                    completion_tokens += c_tokens
                    rows.append(
                        {
                            "arm": arm,
                            "case_id": case_id,
                            "unit_id": unit.get("unit_id"),
                            "leaf_id": unit.get("leaf_id"),
                            "status": "completed",
                            "answerable": answerable,
                            "expected_answerable": expected_answerable,
                            "matches_expected": answerable == expected_answerable,
                            "evidence_cited": evidence_cited,
                            "fail_open": fail_open,
                            "answer_text": str(parsed.get("answer") or "")[:240],
                            "prompt_tokens": p_tokens,
                            "completion_tokens": c_tokens,
                            "total_tokens": p_tokens + c_tokens,
                            "latency_ms": float(response.get("latency_ms") or 0.0),
                        }
                    )
                except Exception as exc:  # pragma: no cover - live provider failure path
                    rows.append(
                        {
                            "arm": arm,
                            "case_id": case_id,
                            "unit_id": unit.get("unit_id"),
                            "leaf_id": unit.get("leaf_id"),
                            "status": "failed",
                            "error": str(exc)[:240],
                            "answerable": False,
                            "expected_answerable": expected_answerable,
                            "matches_expected": False,
                            "evidence_cited": False,
                            "fail_open": False,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "latency_ms": 0.0,
                        }
                    )

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms = [_arm_summary(arm, by_arm.get(arm, [])) for arm in ARMS]
    runtime_exercised = bool(rows) and all(arm["status"] == "completed" for arm in arms)
    total_tokens = prompt_tokens + completion_tokens
    return {
        "schema": SCHEMA,
        "verdict": "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB" if runtime_exercised else "BLOCKED_OR_FAILED",
        "verdict_ceiling": "PROJECTED_LIVE_PROVIDER_ONLY",
        "quality_claim_allowed": False,
        "runtime_exercised": runtime_exercised,
        "provider_call_count": sum(int(arm["provider_call_count"]) for arm in arms),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "models": [model] if runtime_exercised else [],
        "arms": arms,
        "rows": rows,
        "summary": {
            "sample_count": len(selected),
            "start_index": max(0, start_index),
            "planned_arm_count": len(ARMS),
            "provider_call_count": sum(int(arm["provider_call_count"]) for arm in arms),
            "total_tokens": total_tokens,
            "blocker_count": len(blockers),
            "live_runtime_executed": runtime_exercised,
        },
        "blockers": blockers,
        "not_exercised": [
            "production_rag_runtime",
            "runtime_default_install",
            "canonical_truth_write",
            "official_score",
            "production_db_write",
            "release_truth_claim",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "v23_live_provider_shadow_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
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
    parser.add_argument("--near-live-ab", type=Path, default=DEFAULT_NEAR_LIVE_AB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--sample-limit", type=int, default=8)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(
        provider=args.provider,
        model=model,
        timeout_s=args.timeout_s,
    )
    report = build_v23_live_provider_shadow_ab(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        near_live_ab=_read_json(args.near_live_ab),
        sample_limit=args.sample_limit,
        start_index=args.start_index,
        provider_call=provider_call,
        model=model,
        timeout_s=args.timeout_s,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
