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

from scripts.run_luban_p1_strong_go_gate import build_p1_strong_go_package  # noqa: E402
from scripts.run_luban_p2_live_readback_gate import build_p2_live_readback_package  # noqa: E402
from scripts.run_luban_p3_api_readback_gate import build_p3_api_readback_package  # noqa: E402
from scripts.run_luban_p4_ws_readback_gate import build_p4_ws_readback_package  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/nexus_compilation_decision_20260611"
FOUR_ARM_DIR = ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v5_patched_gold"
FOUR_ARM = FOUR_ARM_DIR / "report.json"
FOUR_ARM_CLEAN = (
    ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v3_final/clean_subset_analysis.json"
)
FOUR_ARM_FREEZE = FOUR_ARM_DIR / "freeze_manifest.json"
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


def _p2_live_readback_track(p2_package: dict[str, Any]) -> dict[str, Any]:
    p2 = dict(p2_package.get("p2_live_readback") or {})
    chain = dict(p2_package.get("chain") or {})
    safety = dict(p2_package.get("safety") or {})
    strong = p2.get("verdict") == "STRONG-GO"
    return {
        "status": "local_live_readback_passed" if strong else "local_live_readback_not_passed",
        "phase2_loop_verdict": "STRONG-GO" if strong else "NO-GO",
        "live_readback_exercised": True,
        "live_readback_required_for_go": True,
        "required_readbacks_present": bool(p2.get("required_readbacks_present")),
        "readback_ids": dict(p2.get("readback_ids") or {}),
        "artifact_version": chain.get("artifact_version"),
        "learner_memory_event_ids": list(chain.get("learner_memory_event_ids") or []),
        "weakness_projection_id": chain.get("weakness_projection_id"),
        "next_action_id": chain.get("next_action_id"),
        "shadow_writeback_blocked": bool(p2.get("shadow_writeback_blocked")),
        "release_truth_written": bool(safety.get("canonical_truth_written")),
        "scope": "local_live_readback_not_release_truth",
        "blockers": list(p2.get("blockers") or []),
        "not_release_reasons": [
            "production_write_not_authorized",
            "canonical_truth_write_not_authorized",
            "published_registry_write_not_authorized",
            "real_wechat_package_readback_not_exercised",
        ],
    }


def _p3_api_readback_track(p3_package: dict[str, Any]) -> dict[str, Any]:
    p3 = dict(p3_package.get("p3_api_readback") or {})
    return {
        "verdict": p3.get("verdict"),
        "mode": p3.get("mode"),
        "api_readback_exercised": bool(p3.get("api_readback_exercised")),
        "required_readbacks_present": bool(p3.get("required_readbacks_present")),
        "projection_hash_match": bool(p3.get("projection_hash_match")),
        "readback_ids": dict(p3.get("readback_ids") or {}),
        "api_readbacks": dict(p3_package.get("api_readbacks") or {}),
        "blockers": list(p3.get("blockers") or []),
        "not_release_reasons": [
            "production_write_not_authorized",
            "canonical_truth_write_not_authorized",
            "published_registry_write_not_authorized",
            "real_wechat_package_readback_not_exercised",
            "real_ws_turn_not_exercised",
        ],
    }


def _p4_ws_readback_track(p4_package: dict[str, Any]) -> dict[str, Any]:
    p4 = dict(p4_package.get("p4_ws_readback") or {})
    ws_turn = dict(p4_package.get("ws_turn") or {})
    return {
        "verdict": p4.get("verdict"),
        "mode": p4.get("mode"),
        "ws_turn_exercised": bool(p4.get("ws_turn_exercised")),
        "required_readbacks_present": bool(p4.get("required_readbacks_present")),
        "projection_hash_match": bool(p4.get("projection_hash_match")),
        "readback_ids": dict(p4.get("readback_ids") or {}),
        "ws_turn": {
            "path": ws_turn.get("path"),
            "turn_id": ws_turn.get("turn_id"),
            "result_event_seen": bool(ws_turn.get("result_event_seen")),
            "construction_grading_result_present": bool(
                ws_turn.get("construction_grading_result_present")
            ),
            "learner_memory_event_ids": list(ws_turn.get("learner_memory_event_ids") or []),
        },
        "api_readbacks": dict(p4_package.get("api_readbacks") or {}),
        "blockers": list(p4.get("blockers") or []),
        "not_release_reasons": [
            "production_write_not_authorized",
            "canonical_truth_write_not_authorized",
            "published_registry_write_not_authorized",
            "real_wechat_package_readback_not_exercised",
            "remote_or_production_ws_turn_not_exercised",
        ],
    }


def _p5_real_wechat_track(p5_package: dict[str, Any] | None) -> dict[str, Any] | None:
    if not p5_package:
        return None
    p5 = dict(p5_package.get("p5_real_wechat_package_readback") or {})
    return {
        "verdict": p5.get("verdict"),
        "mode": p5.get("mode"),
        "real_wechat_package_readback_exercised": bool(
            p5.get("real_wechat_package_readback_exercised")
        ),
        "page_grading_to_brain_loop_present": bool(p5.get("page_grading_to_brain_loop_present")),
        "p4_chain_linked": bool(p5.get("p4_chain_linked")),
        "real_wechat_package": dict(p5_package.get("real_wechat_package") or {}),
        "readback_ids": dict(p5_package.get("readback_ids") or {}),
        "blockers": list(p5.get("blockers") or []),
        "not_release_reasons": [
            "production_write_not_authorized",
            "canonical_truth_write_not_authorized",
            "published_registry_write_not_authorized",
            "remote_or_production_ws_turn_not_exercised",
            "human_or_governance_release_signature_missing",
        ],
    }


def _trace_track(trace: dict[str, Any]) -> dict[str, Any]:
    shadow = trace.get("shadow_gate_proof") or {}
    eligible = trace.get("eligible_arm") or {}
    chain = trace.get("chain") or {}
    return {
        "status": "hermetic_trace_passed"
        if shadow.get("shadow_blocked") is True and eligible.get("next_action_present") is True
        else "not_passed",
        "phase2_loop_verdict": "WEAK-GO"
        if shadow.get("shadow_blocked") is True and eligible.get("next_action_present") is True
        else "NO-GO",
        "live_readback_exercised": False,
        "live_readback_required_for_go": True,
        "artifact_version": chain.get("artifact_version"),
        "learner_memory_event_ids": chain.get("learner_memory_event_ids", []),
        "claim_count": eligible.get("claims_count", 0),
        "next_action_present": bool(eligible.get("next_action_present")),
        "shadow_writeback_blocked": bool(shadow.get("shadow_blocked")),
        "release_truth_written": bool(eligible.get("is_release_truth")),
        "scope": "hermetic_local_real_services_not_production_write",
        "not_go_reasons": [
            "live_readback_not_exercised",
            "production_write_not_authorized",
            "canonical_truth_write_not_authorized",
        ],
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


def build_decision_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    p5_package_path: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    report = _read_json(FOUR_ARM)
    clean = _read_json(FOUR_ARM_CLEAN)
    freeze = _read_json(FOUR_ARM_FREEZE)
    m34 = _read_json(M34_GO_NO_GO)
    trace = _read_json(TRACE)
    gold_work_order = _read_json(GOLD_WORK_ORDER)
    p1_package = build_p1_strong_go_package(output_dir=out / "p1_strong_go_gate")
    p2_package = build_p2_live_readback_package(output_dir=out / "p2_live_readback_gate")
    p3_package = build_p3_api_readback_package(output_dir=out / "p3_api_readback_gate")
    p4_package = build_p4_ws_readback_package(output_dir=out / "p4_ws_readback_gate")
    p5_package = _read_json(Path(p5_package_path)) if p5_package_path else None

    m35_track = _m35_track(report, clean, freeze)
    m34_track = _m34_track(m34)
    hermetic_trace_track = _trace_track(trace)
    p2_track = _p2_live_readback_track(p2_package)
    p3_track = _p3_api_readback_track(p3_package)
    p4_track = _p4_ws_readback_track(p4_package)
    p5_track = _p5_real_wechat_track(p5_package)
    flywheel_track = _flywheel_track(gold_work_order)
    phase1_passed = m35_track["status"] == "phase1_shadow_effectiveness_passed"
    p1_strong = (p1_package.get("p1_governed_subset") or {}).get("verdict") == "STRONG-GO"
    p2_strong = (p2_package.get("p2_live_readback") or {}).get("verdict") == "STRONG-GO"
    p3_strong = (p3_package.get("p3_api_readback") or {}).get("verdict") == "STRONG-GO"
    p4_strong = (p4_package.get("p4_ws_readback") or {}).get("verdict") == "STRONG-GO"
    p5_strong = bool(p5_track and p5_track.get("verdict") == "STRONG-GO")
    not_exercised = [
        "production_db_write",
        "canonical_learner_truth_write",
        "published_registry_write",
        "remote_or_aliyun_write",
        "system_wide_m34_default_flip",
        "real_wechat_package_readback",
        "remote_or_production_ws_turn",
        "gpt55_or_claude_api_runtime_arm",
        "human_or_governance_release_signature",
    ]
    if p5_strong:
        not_exercised.remove("real_wechat_package_readback")

    package = {
        "schema_version": "luban_nexus_compilation_decision.v1",
        "generated_at": "2026-06-12",
        "overall": {
            "phase1_nexus_like_scoring": "STRONG-GO" if p1_strong else ("WEAK-GO" if phase1_passed else "NO-GO"),
            "phase1_scope": "governed_subset" if p1_strong else "full_shadow",
            "phase1_full_set_verdict": (p1_package.get("p1_full_set") or {}).get("verdict", "UNKNOWN"),
            "phase1_shadow_verdict": "WEAK-GO" if phase1_passed else "NO-GO",
            "phase2_grading_to_brain_loop": "STRONG-GO" if p2_strong else hermetic_trace_track["phase2_loop_verdict"],
            "phase2_scope": "local_live_readback" if p2_strong else "hermetic_trace",
            "phase3_api_readback": "STRONG-GO" if p3_strong else "NO-GO",
            "phase3_scope": "local_testclient_api_readback" if p3_strong else "not_passed",
            "phase4_ws_readback": "STRONG-GO" if p4_strong else "NO-GO",
            "phase4_scope": "local_testclient_ws_readback" if p4_strong else "not_passed",
            "phase5_real_wechat_package_readback": "STRONG-GO" if p5_strong else (
                "NO-GO" if p5_track else "NOT-RUN"
            ),
            "phase5_scope": "devtools_real_package_page_readback" if p5_strong else (
                "not_passed" if p5_track else "not_run"
            ),
            "release_verdict": "NO-GO",
            "quality_claim_allowed": False,
            "production_default_allowed": False,
            "official_score_allowed": False,
            "is_release_truth": False,
            "reason": (
                "P1 governed scoring, P2 local live-readback, P3 local API readback, and P4 local "
                "TestClient /api/v1/ws readback pass, but full-set release labels, canonical truth, "
                "production writes, published registry, real WeChat entry, and default gates remain closed"
            ),
        },
        "tracks": {
            "p1_strong_go": {
                "verdict": (p1_package.get("p1_governed_subset") or {}).get("verdict"),
                "sample_count": (p1_package.get("p1_governed_subset") or {}).get("sample_count"),
                "quality_claim_allowed": (p1_package.get("p1_governed_subset") or {}).get("quality_claim_allowed"),
                "label_authority": (p1_package.get("p1_governed_subset") or {}).get("label_authority"),
                "blockers": (p1_package.get("p1_governed_subset") or {}).get("blockers", []),
                "full_set_verdict": (p1_package.get("p1_full_set") or {}).get("verdict"),
                "full_set_blockers": (p1_package.get("p1_full_set") or {}).get("blockers", []),
                "artifact_path": str((out / "p1_strong_go_gate" / "p1_strong_go_package.json").relative_to(ROOT))
                if (out / "p1_strong_go_gate").is_relative_to(ROOT)
                else str(out / "p1_strong_go_gate" / "p1_strong_go_package.json"),
            },
            "m35_case_scoring": m35_track,
            "m34_general_knowledge": m34_track,
            "grading_to_brain": p2_track,
            "p2_live_readback": {
                "verdict": (p2_package.get("p2_live_readback") or {}).get("verdict"),
                "mode": (p2_package.get("p2_live_readback") or {}).get("mode"),
                "convergence_claim_allowed": (p2_package.get("p2_live_readback") or {}).get(
                    "convergence_claim_allowed"
                ),
                "required_readbacks_present": (p2_package.get("p2_live_readback") or {}).get(
                    "required_readbacks_present"
                ),
                "readback_ids": (p2_package.get("p2_live_readback") or {}).get("readback_ids"),
                "blockers": (p2_package.get("p2_live_readback") or {}).get("blockers", []),
                "artifact_path": str((out / "p2_live_readback_gate" / "p2_live_readback_package.json").relative_to(ROOT))
                if (out / "p2_live_readback_gate").is_relative_to(ROOT)
                else str(out / "p2_live_readback_gate" / "p2_live_readback_package.json"),
            },
            "p3_api_readback": {
                **p3_track,
                "artifact_path": str((out / "p3_api_readback_gate" / "p3_api_readback_package.json").relative_to(ROOT))
                if (out / "p3_api_readback_gate").is_relative_to(ROOT)
                else str(out / "p3_api_readback_gate" / "p3_api_readback_package.json"),
            },
            "p4_ws_readback": {
                **p4_track,
                "artifact_path": str((out / "p4_ws_readback_gate" / "p4_ws_readback_package.json").relative_to(ROOT))
                if (out / "p4_ws_readback_gate").is_relative_to(ROOT)
                else str(out / "p4_ws_readback_gate" / "p4_ws_readback_package.json"),
            },
            "grading_to_brain_hermetic_source": hermetic_trace_track,
            "compiler_feedback_flywheel": flywheel_track,
        },
        "not_exercised": not_exercised,
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
    if p5_track:
        package["tracks"]["p5_real_wechat_package_readback"] = p5_track

    out.mkdir(parents=True, exist_ok=True)
    (out / "decision_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--p5-package-path", default="")
    args = parser.parse_args()
    package = build_decision_package(
        output_dir=args.output_dir,
        p5_package_path=args.p5_package_path or None,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
