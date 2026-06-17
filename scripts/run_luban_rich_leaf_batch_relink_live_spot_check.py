#!/usr/bin/env python3
"""Live-provider spot check for batch-relinked runtime units.

Samples relinked units from a batch relink report and asks a real provider,
using the same prompt shape as the v2.3 live shadow A/B (rich context arm and
artifact-first guard arm), whether the repaired compiled context can answer the
leaf's knowledge question. Projected live-provider trace only: no production
RAG, no runtime install, no canonical writes.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from statistics import mean
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import (  # noqa: E402
    PROVIDER_DEFAULTS,
    _openai_compat_provider,
    _parse_json_object,
)
from scripts.run_luban_rich_leaf_v23_live_provider_shadow_ab import _messages  # noqa: E402

SCHEMA = "luban_rich_leaf_batch_relink_live_spot_check.v1"
RELINK_SCHEMA = "luban_rich_leaf_batch_relink_candidates.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
ARMS = ("rich_leaf_v23_context_live", "artifact_first_guard_live")

DEFAULT_RELINK_REPORT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v232_batch_relink_20260612/batch_relink_report.json"
)
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v232_batch_relink_20260612/runtime_token_pack_v232_candidate.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v232_batch_relink_20260612/batch_relink_live_spot_check.json"
)

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "batch_relink_live_spot_check": True,
    "runtime_install_allowed": False,
    "production_default": False,
    "canonical_pointer_written": False,
    "release_truth_claimed": False,
    "quality_claim_allowed": False,
}
SAFETY = {
    "canonical_truth_written": False,
    "official_score_allowed": False,
    "installed_runtime_supply": False,
    "production_write_count": 0,
    "release_truth_claimed": False,
}
NOT_EXERCISED = [
    "production_rag_runtime",
    "runtime_default_install",
    "canonical_truth_write",
    "official_score",
    "production_db_write",
    "release_truth_claim",
    "non_sampled_relinked_units",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_batch_relink_live_spot_check(
    *,
    relink_report: dict[str, Any],
    runtime_token_pack: dict[str, Any],
    sample_size: int,
    seed: int,
    provider_call: Any,
    model: str,
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    blockers: list[str] = []
    if relink_report.get("schema") != RELINK_SCHEMA:
        blockers.append(f"relink_report_schema_mismatch:{relink_report.get('schema')}")
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if provider_call is None:
        blockers.append("provider_call_not_configured")

    units_by_id = {
        str(u.get("unit_id")): u
        for u in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(u, dict) and u.get("unit_id")
    }
    relinked_ids = [str(r.get("unit_id")) for r in relink_report.get("relinked") or [] if r.get("unit_id")]
    sampled = sorted(relinked_ids)
    if sample_size < len(sampled):
        rng = random.Random(seed)
        sampled = sorted(rng.sample(sampled, sample_size))
    if not sampled:
        blockers.append("no_relinked_units_to_sample")

    rows: list[dict[str, Any]] = []
    if not blockers:
        for unit_id in sampled:
            unit = units_by_id.get(unit_id)
            if unit is None:
                blockers.append(f"{unit_id}:unit_missing_in_pack")
                continue
            for arm in ARMS:
                case_id = f"relink_spot_{unit_id}"
                messages = _messages(arm, case_id=case_id, proxy_row={"answerable": True}, unit=unit)
                try:
                    response = provider_call(model, messages, timeout_s=timeout_s)
                    parsed = _parse_json_object(str(response.get("content") or ""))
                    p_tokens = int(response.get("prompt_tokens") or 0)
                    c_tokens = int(response.get("completion_tokens") or 0)
                    rows.append(
                        {
                            "arm": arm,
                            "unit_id": unit_id,
                            "leaf_id": unit.get("leaf_id"),
                            "status": "completed",
                            "answerable": bool(parsed.get("answerable")),
                            "expected_answerable": True,
                            "matches_expected": bool(parsed.get("answerable")),
                            "evidence_cited": bool(parsed.get("evidence_cited")),
                            "fail_open": bool(parsed.get("fail_open")),
                            "answer_text": str(parsed.get("answer") or "")[:200],
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
                            "unit_id": unit_id,
                            "leaf_id": unit.get("leaf_id"),
                            "status": "failed",
                            "error": str(exc)[:200],
                            "answerable": False,
                            "expected_answerable": True,
                            "matches_expected": False,
                            "evidence_cited": False,
                            "fail_open": False,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "latency_ms": 0.0,
                        }
                    )

    completed = [r for r in rows if r.get("status") == "completed"]
    runtime_exercised = bool(rows) and len(completed) == len(rows)
    summary = {
        "sampled_unit_count": len(sampled),
        "relinked_unit_count": len(relinked_ids),
        "provider_call_count": len(completed),
        "accuracy_rate": round(mean([1.0 if r["matches_expected"] else 0.0 for r in completed]), 4) if completed else 0.0,
        "fail_open_rate": round(mean([1.0 if r["fail_open"] else 0.0 for r in completed]), 4) if completed else 0.0,
        "evidence_citation_rate": round(mean([1.0 if r["evidence_cited"] else 0.0 for r in completed]), 4) if completed else 0.0,
        "total_tokens": sum(int(r["total_tokens"]) for r in completed),
        "mean_latency_ms": round(mean([float(r["latency_ms"]) for r in completed]), 2) if completed else 0.0,
        "blocker_count": len(blockers),
        "production_write_count": 0,
    }
    return {
        "schema": SCHEMA,
        "verdict": "PASS_BATCH_RELINK_LIVE_SPOT_CHECK" if runtime_exercised else "BLOCKED_OR_FAILED",
        "verdict_ceiling": "PROJECTED_LIVE_PROVIDER_ONLY",
        "quality_claim_allowed": False,
        "runtime_exercised": runtime_exercised,
        "models": [model] if runtime_exercised else [],
        "sampled_unit_ids": sampled,
        "rows": rows,
        "summary": summary,
        "blockers": blockers,
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relink-report", type=Path, default=DEFAULT_RELINK_REPORT)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260612)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--no-provider-call", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(
        provider=args.provider,
        model=model,
        timeout_s=args.timeout_s,
    )
    report = build_batch_relink_live_spot_check(
        relink_report=_read_json(args.relink_report),
        runtime_token_pack=_read_json(args.runtime_token_pack),
        sample_size=args.sample_size,
        seed=args.seed,
        provider_call=provider_call,
        model=model,
        timeout_s=args.timeout_s,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"], "blockers": report["blockers"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
