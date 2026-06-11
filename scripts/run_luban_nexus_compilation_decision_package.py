#!/usr/bin/env python3
"""Aggregate the Nexus-like compilation status into one honest decision package.

This runner is read-only over existing artifacts. It does not promote labels,
write canonical learner truth, publish registries, call providers, or touch
remote state. Its job is to make the current compilation state machine-readable:
what has passed as shadow evidence, what remains NO-GO, and which work orders
must feed the next compiler loop.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/nexus_compilation_decision_20260611"
FOUR_ARM = ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v3_final/report.json"
FOUR_ARM_CLEAN = (
    ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v3_final/clean_subset_analysis.json"
)
FOUR_ARM_FREEZE = (
    ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v3_final/freeze_manifest.json"
)
GOLD_WORK_ORDER = ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/gold_readjudication_work_order.json"
M34_GO_NO_GO = ROOT / "artifacts/luban_grading_artifacts/general_knowledge_dividend_m34_20260609/go_no_go_m34.json"
M34_WORK_ORDERS = (
    ROOT / "artifacts/luban_grading_artifacts/general_knowledge_dividend_m34_20260609/compiler_source_work_orders_m34.jsonl"
)
TRACE = ROOT / "artifacts/luban_grading_artifacts/judge_grading_to_brain_trace_20260611_v3_final/loop_trace.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _metric_delta(new: dict[str, Any], old: dict[str, Any], key: str) -> float | None:
    if new.get(key) is None or old.get(key) is None:
        return None
    return round(float(new[key]) - float(old[key]), 6)


def _m35_track(report: dict[str, Any], clean: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    judge = summary["artifact_first_llm_judge"]
    legacy = summary["legacy"]
    rag = summary["current_rag_offline"]
    compiled = summary["artifact_first_compiled"]
    phase1 = report["phase1_criteria_check"]
    shadow_passed = (
        phase1.get("judge_mae_not_worse_than_legacy") is True
        and phase1.get("judge_fail_open_not_higher_than_legacy") is True
        and report.get("quality_claim_allowed") is False
        and (report.get("safety") or {}).get("is_release_truth") is False
    )
    return {
        "status": "phase1_shadow_effectiveness_passed" if shadow_passed else "phase1_shadow_effectiveness_not_passed",
        "verdict_ceiling": report.get("verdict_ceiling"),
        "quality_claim_allowed": bool(report.get("quality_claim_allowed")),
        "sample_count": report.get("sample_count"),
        "label_mix": (report.get("fixture") or {}).get("label_authority_counts", {}),
        "legacy": legacy,
        "current_rag_offline": rag,
        "artifact_first_compiled": compiled,
        "artifact_first_llm_judge": judge,
        "judge_vs_legacy": {
            "score_mae_delta": _metric_delta(judge, legacy, "score_mae"),
            "fail_open_delta": _metric_delta(judge, legacy, "fail_open_rate"),
            "token_delta": _metric_delta(judge, legacy, "mean_token"),
            "latency_ms_delta": _metric_delta(judge, legacy, "mean_latency_ms"),
        },
        "judge_vs_current_rag_offline": {
            "score_mae_delta": _metric_delta(judge, rag, "score_mae"),
            "fail_open_delta": _metric_delta(judge, rag, "fail_open_rate"),
            "token_delta": _metric_delta(judge, rag, "mean_token"),
        },
        "clean_subset": {
            "exclusion": clean.get("exclusion"),
            "summary": (clean.get("clean_summary") or {}).get("artifact_first_llm_judge"),
            "disputed_bucket": (clean.get("clean_disputed") or {}).get("artifact_first_llm_judge"),
        },
        "provider": report.get("provider", {}),
        "freeze_manifest": str(FOUR_ARM_FREEZE.relative_to(ROOT)),
        "frozen_code_hashes": freeze.get("code", {}),
        "not_release_reasons": [
            "verdict_ceiling_is_directional_shadow",
            "quality_claim_allowed_false",
            "ai_council_directional_labels_are_not_release_truth",
            "gold_readjudication_work_order_open",
            "no_governance_signature_for_official_score",
        ],
    }


def _m34_track(m34: dict[str, Any]) -> dict[str, Any]:
    production_default = str(m34.get("production_default") or "")
    blockers: list[str] = []
    if production_default != "enabled":
        blockers.append("online_shadow_or_compiler_repair_pending")
    if m34.get("system_wide_default_gate"):
        blockers.append(str(m34["system_wide_default_gate"]))
    work_order_count = _count_jsonl(M34_WORK_ORDERS)
    if work_order_count:
        blockers.append("source_path_conflict_work_orders_open")
    return {
        "capability_verdict": m34.get("verdict"),
        "system_wide_default": "GO" if production_default == "enabled" and not blockers else "NO-GO",
        "production_default": production_default,
        "default_cohort_scope": m34.get("default_cohort_scope"),
        "work_order_count": work_order_count,
        "work_orders_path": str(M34_WORK_ORDERS.relative_to(ROOT)),
        "blockers": list(dict.fromkeys(blockers)),
        "canonical_truth_written": bool(m34.get("canonical_truth_written")),
        "production_write_count": int(m34.get("production_write_count") or 0),
    }


def _trace_track(trace: dict[str, Any]) -> dict[str, Any]:
    shadow = trace.get("shadow_gate_proof") or {}
    eligible = trace.get("eligible_arm") or {}
    chain = trace.get("chain") or {}
    return {
        "status": "hermetic_trace_passed"
        if shadow.get("shadow_blocked") is True and eligible.get("next_action_present") is True
        else "not_passed",
        "artifact_version": chain.get("artifact_version"),
        "learner_memory_event_ids": chain.get("learner_memory_event_ids", []),
        "claim_count": eligible.get("claims_count", 0),
        "next_action_present": bool(eligible.get("next_action_present")),
        "shadow_writeback_blocked": bool(shadow.get("shadow_blocked")),
        "release_truth_written": bool(eligible.get("is_release_truth")),
        "scope": "hermetic_local_real_services_not_production_write",
    }


def _flywheel_track(gold_work_order: dict[str, Any]) -> dict[str, Any]:
    open_work_orders: list[dict[str, Any]] = []
    if gold_work_order.get("status") == "open":
        open_work_orders.append({
            "work_order_id": gold_work_order.get("work_order_id"),
            "type": "gold_readjudication",
            "path": str(GOLD_WORK_ORDER.relative_to(ROOT)),
            "damaged_row_count": len((gold_work_order.get("scope") or {}).get("damaged_rows") or []),
        })
    m34_count = _count_jsonl(M34_WORK_ORDERS)
    if m34_count:
        open_work_orders.append({
            "work_order_id": "M34_SOURCE_PATH_CONFLICTS",
            "type": "compiler_source_repair",
            "path": str(M34_WORK_ORDERS.relative_to(ROOT)),
            "row_count": m34_count,
        })
    return {
        "status": "partial" if open_work_orders else "ready_for_next_recompile",
        "open_work_orders": open_work_orders,
        "next_required_loop": [
            "execute_gold_readjudication_without_overwriting_v1",
            "repair_m34_source_path_conflicts",
            "recompile_signed_candidates",
            "rerun_four_arm_ab_and_online_shadow",
        ],
        "release_truth_promotion_allowed": False,
    }


def build_decision_package(*, output_dir: str | Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    report = _read_json(FOUR_ARM)
    clean = _read_json(FOUR_ARM_CLEAN)
    freeze = _read_json(FOUR_ARM_FREEZE)
    m34 = _read_json(M34_GO_NO_GO)
    trace = _read_json(TRACE)
    gold_work_order = _read_json(GOLD_WORK_ORDER)

    m35_track = _m35_track(report, clean, freeze)
    m34_track = _m34_track(m34)
    trace_track = _trace_track(trace)
    flywheel_track = _flywheel_track(gold_work_order)
    phase1_passed = m35_track["status"] == "phase1_shadow_effectiveness_passed"

    package = {
        "schema_version": "luban_nexus_compilation_decision.v1",
        "generated_at": "2026-06-11",
        "overall": {
            "phase1_shadow_verdict": "WEAK-GO" if phase1_passed else "NO-GO",
            "release_verdict": "NO-GO",
            "quality_claim_allowed": False,
            "production_default_allowed": False,
            "official_score_allowed": False,
            "is_release_truth": False,
            "reason": (
                "case scoring effect is directionally strong in shadow, but labels are not release truth "
                "and compiler/governance/default gates remain open"
            ),
        },
        "tracks": {
            "m35_case_scoring": m35_track,
            "m34_general_knowledge": m34_track,
            "grading_to_brain": trace_track,
            "compiler_feedback_flywheel": flywheel_track,
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "system_wide_m34_default_flip",
            "gpt55_or_claude_api_runtime_arm",
            "human_or_governance_release_signature",
        ],
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decision_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    package = build_decision_package(output_dir=args.output_dir)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
