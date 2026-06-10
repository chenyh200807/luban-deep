#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCENARIO_PRESETS = {
    "standard_100k": {
        "member_count": 50_000,
        "active_rate": 0.20,
        "attempts_per_active_member_per_month": 10,
    },
    "heavy_1m": {
        "member_count": 50_000,
        "active_rate": 0.50,
        "attempts_per_active_member_per_month": 40,
    },
    "peak_3m": {
        "member_count": 50_000,
        "active_rate": 0.75,
        "attempts_per_active_member_per_month": 80,
    },
}


def estimate_m35_capacity(
    *,
    member_count: int,
    active_rate: float,
    attempts_per_active_member_per_month: int,
    avg_points_per_attempt: int,
    evidence_bytes_per_point: int,
    prompt_trace_bytes_per_attempt: int,
    global_artifact_count: int,
    avg_artifact_bytes: int,
) -> dict[str, Any]:
    active_members = int(member_count * active_rate)
    monthly_attempts = active_members * attempts_per_active_member_per_month
    monthly_evidence_bytes = monthly_attempts * avg_points_per_attempt * evidence_bytes_per_point
    monthly_trace_bytes = monthly_attempts * prompt_trace_bytes_per_attempt
    global_artifact_bytes = global_artifact_count * avg_artifact_bytes

    return {
        "active_members": active_members,
        "monthly_attempts": monthly_attempts,
        "monthly_evidence_storage_mb": round(monthly_evidence_bytes / 1024 / 1024, 2),
        "monthly_trace_storage_mb": round(monthly_trace_bytes / 1024 / 1024, 2),
        "global_artifact_storage_mb": round(global_artifact_bytes / 1024 / 1024, 2),
        "primary_growth_driver": "attempt_evidence_and_trace_not_global_artifacts",
        "per_user_artifact_copy_allowed": False,
        "requires_partitioning": monthly_attempts >= 100_000,
        "trace_retention_policy": "ttl_or_cold_storage",
    }


def estimate_m35_capacity_scenarios() -> dict[str, Any]:
    scenario_results: dict[str, dict[str, Any]] = {}
    for name, preset in SCENARIO_PRESETS.items():
        scenario_results[name] = estimate_m35_capacity(
            member_count=preset["member_count"],
            active_rate=preset["active_rate"],
            attempts_per_active_member_per_month=preset["attempts_per_active_member_per_month"],
            avg_points_per_attempt=8,
            evidence_bytes_per_point=360,
            prompt_trace_bytes_per_attempt=12_000,
            global_artifact_count=500,
            avg_artifact_bytes=14_000,
        )

    return {
        "scenario_results": scenario_results,
        "max_monthly_attempts": max(row["monthly_attempts"] for row in scenario_results.values()),
        "per_user_artifact_copy_allowed": False,
        "readiness_claim": "estimate_only_not_load_test",
        "next_required_gate": "load_test_hot_read_models_and_storage",
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--member-count", type=int, default=50_000)
    parser.add_argument("--scenario", choices=["standard_100k", "heavy_1m", "peak_3m", "all"], default="all")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.scenario == "all":
        estimate = estimate_m35_capacity_scenarios()
    else:
        preset = dict(SCENARIO_PRESETS[args.scenario])
        preset["member_count"] = args.member_count
        estimate = estimate_m35_capacity(
            member_count=preset["member_count"],
            active_rate=preset["active_rate"],
            attempts_per_active_member_per_month=preset["attempts_per_active_member_per_month"],
            avg_points_per_attempt=8,
            evidence_bytes_per_point=360,
            prompt_trace_bytes_per_attempt=12_000,
            global_artifact_count=500,
            avg_artifact_bytes=14_000,
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(estimate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
