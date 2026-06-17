#!/usr/bin/env python3
"""Frozen-v1 full-pack live-provider four-arm shadow A/B (sampled leaves).

Samples N leaves (seeded) from the frozen-v1 full compile pack and runs the
four projection arms against a real provider. Every sampled leaf carries real
source evidence, so expected_answerable is True for all arms — no near-live
dependency. This is a projected live-provider trace: it never calls production
RAG, never installs runtime defaults, never writes canonical truth.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import (  # noqa: E402
    PROVIDER_DEFAULTS,
    _openai_compat_provider,
    _parse_json_object,
)

SCHEMA = "luban_rich_leaf_frozen_v1_live_ab.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
EXPECTED_PACK_VERSION = "v3.0_frozen_v1_full_compile"
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613/runtime_token_pack_v30_frozen_full.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613/frozen_v1_live_ab_sample100.json"
)
ARMS = (
    "current_rag_projection_live",
    "legacy_keyword_projection_live",
    "rich_leaf_context_live",
    "artifact_first_guard_live",
)
DEFAULT_SEED = 20260613

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


def _sample_units(runtime_token_pack: dict[str, Any], *, sample_size: int, seed: int) -> list[dict[str, Any]]:
    units = [
        unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id") and unit.get("leaf_id")
    ]
    units.sort(key=lambda u: str(u["unit_id"]))
    if len(units) <= sample_size:
        return units
    return random.Random(seed).sample(units, sample_size)


def _compact_context(compiled_context: dict[str, Any], *, max_items_per_family: int) -> dict[str, list[str]]:
    compact: dict[str, list[str]] = {}
    for family in ("concepts", "definitions", "rules", "procedures", "numeric_constraints", "exam_patterns", "teaching_cards"):
        values = [str(item) for item in compiled_context.get(family) or [] if str(item).strip()]
        if values:
            compact[family] = values[:max_items_per_family]
    return compact


def _arm_context(arm: str, *, unit: dict[str, Any]) -> dict[str, Any]:
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
            "retrieved_evidence": [source_pointer],
            "retrieval_projection": "current_rag_proxy_not_production_rag",
        }
    if arm == "legacy_keyword_projection_live":
        return {
            "mode": arm,
            "leaf_name_path": unit.get("leaf_name_path"),
            "keywords": _compact_context(compiled_context, max_items_per_family=1),
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


def _messages(arm: str, *, case_id: str, unit: dict[str, Any]) -> list[dict[str, str]]:
    leaf_name = str(unit.get("leaf_name_path") or unit.get("leaf_id") or "该知识点")
    payload = {
        "case_id": case_id,
        "arm": arm,
        "question": f"请用给定证据概述「{leaf_name}」的核心定义、规则或考试要点。",
        "task": "Decide whether the provided context is sufficient to answer this concrete construction-exam knowledge question.",
        "context": _arm_context(arm, unit=unit),
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


def _run_one(
    *,
    arm: str,
    unit: dict[str, Any],
    provider_call: ProviderCall,
    model: str,
    timeout_s: float,
) -> dict[str, Any]:
    case_id = str(unit.get("unit_id"))
    base = {
        "arm": arm,
        "case_id": case_id,
        "unit_id": unit.get("unit_id"),
        "leaf_id": unit.get("leaf_id"),
        "expected_answerable": True,
    }
    messages = _messages(arm, case_id=case_id, unit=unit)
    try:
        response = provider_call(model, messages, timeout_s=timeout_s)
        parsed = _parse_json_object(str(response.get("content") or ""))
        answerable = bool(parsed.get("answerable"))
        p_tokens = int(response.get("prompt_tokens") or 0)
        c_tokens = int(response.get("completion_tokens") or 0)
        return {
            **base,
            "status": "completed",
            "answerable": answerable,
            "matches_expected": answerable is True,
            "evidence_cited": bool(parsed.get("evidence_cited")),
            "fail_open": bool(parsed.get("fail_open")),
            "answer_text": str(parsed.get("answer") or "")[:240],
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens,
            "latency_ms": float(response.get("latency_ms") or 0.0),
        }
    except Exception as exc:  # pragma: no cover - live provider failure path
        return {
            **base,
            "status": "failed",
            "error": str(exc)[:240],
            "answerable": False,
            "matches_expected": False,
            "evidence_cited": False,
            "fail_open": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0.0,
        }


def _arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    if not rows:
        status = "failed"
    elif len(completed) == len(rows):
        status = "completed"
    elif len(completed) >= 0.9 * len(rows):
        status = "completed_with_errors"
    else:
        status = "failed"
    return {
        "arm": arm,
        "status": status,
        "sample_count": len(rows),
        "provider_call_count": len(completed),
        "failed_call_count": len(rows) - len(completed),
        "accuracy_rate": round(mean([1.0 if row.get("matches_expected") else 0.0 for row in completed]), 4) if completed else 0.0,
        "answerable_rate": round(mean([1.0 if row.get("answerable") else 0.0 for row in completed]), 4) if completed else 0.0,
        "evidence_citation_rate": round(mean([1.0 if row.get("evidence_cited") else 0.0 for row in completed]), 4) if completed else 0.0,
        "fail_open_rate": round(mean([1.0 if row.get("fail_open") else 0.0 for row in completed]), 4) if completed else 0.0,
        "mean_prompt_tokens": round(mean([int(row.get("prompt_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_completion_tokens": round(mean([int(row.get("completion_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_total_tokens": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
    }


def build_frozen_v1_live_ab(
    *,
    runtime_token_pack: dict[str, Any],
    sample_size: int,
    seed: int,
    provider_call: ProviderCall | None,
    model: str,
    timeout_s: float = 45.0,
    max_workers: int = 8,
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if runtime_token_pack.get("version") != EXPECTED_PACK_VERSION:
        blockers.append(f"runtime_token_pack_version_mismatch:{runtime_token_pack.get('version')}")
    if runtime_token_pack.get("status") != "candidate_ready_for_shadow_ab_full_accounted":
        blockers.append(f"runtime_token_pack_status_invalid:{runtime_token_pack.get('status')}")
    blockers.extend(_safety_blockers("runtime_token_pack", runtime_token_pack))
    if provider_call is None:
        blockers.append("provider_call_not_configured")

    sampled = _sample_units(runtime_token_pack, sample_size=sample_size, seed=seed)
    if not sampled:
        blockers.append("no_units_sampled")

    rows: list[dict[str, Any]] = []
    if not blockers and provider_call is not None:
        tasks = [(unit, arm) for unit in sampled for arm in ARMS]
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            rows = list(
                pool.map(
                    lambda pair: _run_one(
                        arm=pair[1], unit=pair[0], provider_call=provider_call, model=model, timeout_s=timeout_s
                    ),
                    tasks,
                )
            )
        rows.sort(key=lambda r: (str(r.get("case_id")), ARMS.index(str(r.get("arm")))))

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms = [_arm_summary(arm, by_arm.get(arm, [])) for arm in ARMS]
    runtime_exercised = bool(rows) and all(arm["status"] != "failed" for arm in arms)
    prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in rows)
    completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in rows)
    total_tokens = prompt_tokens + completion_tokens
    provider_call_count = sum(int(arm["provider_call_count"]) for arm in arms)
    return {
        "schema": SCHEMA,
        "verdict": "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB" if runtime_exercised else "BLOCKED_OR_FAILED",
        "verdict_ceiling": "PROJECTED_LIVE_PROVIDER_ONLY",
        "quality_claim_allowed": False,
        "runtime_exercised": runtime_exercised,
        "provider_call_count": provider_call_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "models": [model] if runtime_exercised else [],
        "sample_seed": seed,
        "arms": arms,
        "rows": rows,
        "summary": {
            "sample_count": len(sampled),
            "planned_arm_count": len(ARMS),
            "provider_call_count": provider_call_count,
            "failed_call_count": sum(int(arm["failed_call_count"]) for arm in arms),
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
            "frozen_v1_live_ab": True,
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(
        provider=args.provider,
        model=model,
        timeout_s=args.timeout_s,
    )
    report = build_frozen_v1_live_ab(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        sample_size=args.sample_size,
        seed=args.seed,
        provider_call=provider_call,
        model=model,
        timeout_s=args.timeout_s,
        max_workers=args.max_workers,
    )
    _write_json(args.output, report)
    print(
        json.dumps(
            {"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"], "blockers": report["blockers"]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
