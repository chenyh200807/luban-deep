#!/usr/bin/env python3
"""M26 A/B + real-chain QA runner.

Builds the seven-scenario matrix (historical objective, governed objective invalid, case in
registry, case variant, open construction concept, user-pasted unknown, retest/next-action) and
compares four configs (v0 registry-only, old RAG/KB v5 context, v1 official mode, v1 open-world
diagnostic) on quality/correctness/latency/cost/fallback/satisfaction proxies. Hermetic by default;
``--run-live`` is gated and records a precise live blocker when creds are absent — it never fakes a
live result.

This reuses the real M26 surfaces via ``run_luban_compiled_context_open_world_m26`` so the A/B
report and the closure runner cannot drift.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = (
    _REPO / "artifacts" / "luban_grading_artifacts"
    / "compiled_context_open_world_m26_20260606"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "m26_runner_ab", _REPO / "scripts" / "run_luban_compiled_context_open_world_m26.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


SCENARIO_MATRIX = [
    {"id": "historical_objective", "lane": "objective", "in_bank": True},
    {"id": "governed_objective_invalid", "lane": "objective", "in_bank": False},
    {"id": "case_in_registry", "lane": "case", "in_bank": True},
    {"id": "case_variant", "lane": "open_world", "in_bank": False},
    {"id": "open_construction_concept", "lane": "open_world", "in_bank": False},
    {"id": "user_pasted_unknown", "lane": "open_world", "in_bank": False},
    {"id": "retest_next_action", "lane": "learning_brain", "in_bank": True},
]


def build_report(*, run_live: bool = False) -> dict[str, Any]:
    runner = _load_runner()
    open_world_rows = runner.run_open_world_lane()
    objective = runner.run_objective_lanes()
    ab = runner.run_ab(open_world_rows, objective)
    consumer = runner.run_consumer_ledger()
    lb = runner.run_learning_brain(objective)

    live_blocker = ""
    if run_live and not os.getenv("DASHSCOPE_API_KEY"):
        live_blocker = "--run-live requested but DASHSCOPE_API_KEY/DeepSeek creds absent; " \
            "live model quality + token cost cannot be measured. Reporting hermetic proxies only."

    return {
        "scenario_matrix": SCENARIO_MATRIX,
        "ab": ab,
        "consumer_single_schema": consumer["single_schema"],
        "learning_brain": lb,
        "run_live_requested": run_live,
        "live_blocker": live_blocker or ab["live_blocker"],
        "fallback_summary": {
            "v0_registry_only": "refuses not-in-bank (refusal_rate=1.0)",
            "v1_open_world_diagnostic": "fail-open diagnosis, refusal_rate=0",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--out", default=str(ARTIFACT_DIR / "ab_real_chain_qa_report_m26.json"))
    args = parser.parse_args()
    report = build_report(run_live=args.run_live)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"scenarios": len(report["scenario_matrix"]),
                      "live_blocker": bool(report["live_blocker"]), "out": str(out)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
