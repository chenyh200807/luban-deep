#!/usr/bin/env python3
"""Build the R6 release decision package for the scoring artifact engine.

This runner is read-only over release evidence. It may write its own local
artifact package, but it never publishes a registry, writes canonical learner
truth, flips defaults, calls providers, or touches Aliyun/remote hosts.
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

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/r6_release_decision_package_20260612"
P5_DECISION = ROOT / "artifacts/luban_grading_artifacts/nexus_compilation_decision_20260612_p5_real_wechat/decision_package.json"
CACHED_AB = ROOT / "artifacts/luban_grading_artifacts/four_arm_ab_20260611/live_full_162_v5_patched_gold/report.json"
P5_PACKAGE = ROOT / (
    "artifacts/luban_grading_artifacts/p5_real_wechat_package_readback_20260612/"
    "p5_real_wechat_package_readback_package.json"
)
PREFLIGHT_ROOT = ROOT / "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608"
G1_LIMITED_DEFAULT = PREFLIGHT_ROOT / "G1_LIMITED_DEFAULT_PREFLIGHT.json"
G2_BROAD_DEFAULT = PREFLIGHT_ROOT / "G2_BROAD_DEFAULT_PREFLIGHT.json"
G3_PUBLISHED_REGISTRY = PREFLIGHT_ROOT / "G3_PUBLISHED_REGISTRY_PREFLIGHT.json"
G4_CANONICAL_TRUTH = PREFLIGHT_ROOT / "G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.json"


def _read_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def _rel(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _none_writes(*payloads: dict[str, Any]) -> bool:
    for payload in payloads:
        if bool(payload.get("canonical_truth_written")):
            return False
        if bool(payload.get("published_registry_executed")):
            return False
        if int(payload.get("production_write_count") or 0) != 0:
            return False
        if int(payload.get("remote_write_count") or 0) != 0:
            return False
    return True


def _cached_ab_track(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    return {
        "status": "DIRECTIONAL_SHADOW_PASS"
        if report.get("quality_claim_allowed") is False
        and report.get("verdict_ceiling") == "DIRECTIONAL_SHADOW"
        else "NOT_READY",
        "artifact_path": _rel(CACHED_AB),
        "sample_count": report.get("sample_count"),
        "quality_claim_allowed": bool(report.get("quality_claim_allowed")),
        "verdict_ceiling": report.get("verdict_ceiling"),
        "phase1_criteria_check": dict(report.get("phase1_criteria_check") or {}),
        "legacy": dict(summary.get("legacy") or {}),
        "current_rag_offline": dict(summary.get("current_rag_offline") or {}),
        "artifact_first_compiled": dict(summary.get("artifact_first_compiled") or {}),
        "artifact_first_llm_judge": dict(summary.get("artifact_first_llm_judge") or {}),
        "release_ceiling_reason": [
            "cached_ab_proves_directional_artifact_first_effectiveness",
            "quality_claim_allowed_false",
            "directional_shadow_is_not_release_truth",
        ],
    }


def _p5_track(p5_package: dict[str, Any]) -> dict[str, Any]:
    p5 = dict(p5_package.get("p5_real_wechat_package_readback") or {})
    return {
        "status": "STRONG-GO" if p5.get("verdict") == "STRONG-GO" else "NO-GO",
        "artifact_path": _rel(P5_PACKAGE),
        "mode": p5.get("mode"),
        "real_wechat_package_readback_exercised": bool(
            p5.get("real_wechat_package_readback_exercised")
        ),
        "page_grading_to_brain_loop_present": bool(p5.get("page_grading_to_brain_loop_present")),
        "p4_chain_linked": bool(p5.get("p4_chain_linked")),
        "real_wechat_package": dict(p5_package.get("real_wechat_package") or {}),
        "readback_ids": dict(p5_package.get("readback_ids") or {}),
        "blockers": list(p5.get("blockers") or []),
    }


def _gate_status(gate: dict[str, Any]) -> str:
    if not _none_writes(gate):
        return "PREFLIGHT_INVALID_SIDE_EFFECT_DETECTED"
    if gate.get("verdict") == "ready_for_user_authorization":
        return "PREFLIGHT_READY_NOT_EXECUTED"
    return "PREFLIGHT_BLOCKED_NOT_EXECUTED"


def _gate_track(gate: dict[str, Any], *, artifact_path: Path) -> dict[str, Any]:
    return {
        "status": _gate_status(gate),
        "artifact_path": _rel(artifact_path),
        "gate_id": gate.get("gate_id"),
        "verdict": gate.get("verdict"),
        "scope": gate.get("scope"),
        "execution_mode": gate.get("execution_mode"),
        "promotion_path": gate.get("promotion_path"),
        "required_authorization": gate.get("required_authorization"),
        "action_allowed_without_authorization": False,
        "published_registry_executed": bool(gate.get("published_registry_executed")),
        "canonical_truth_written": bool(gate.get("canonical_truth_written")),
        "production_write_count": int(gate.get("production_write_count") or 0),
        "remote_write_count": int(gate.get("remote_write_count") or 0),
        "preconditions": dict(gate.get("preconditions") or {}),
        "evidence_refs": list(gate.get("evidence_refs") or []),
        "missing_evidence_refs": list(gate.get("missing_evidence_refs") or []),
        "single_authority": dict(gate.get("single_authority") or {}),
        "stop_conditions": list(gate.get("stop_conditions") or []),
        "blocking_reason": gate.get("blocking_reason", ""),
    }


def _system_wide_default_track(g1: dict[str, Any], g2: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "PREFLIGHT_ONLY_NOT_EXECUTED",
        "action_allowed_without_authorization": False,
        "limited_default": _gate_track(g1, artifact_path=G1_LIMITED_DEFAULT),
        "broad_default": _gate_track(g2, artifact_path=G2_BROAD_DEFAULT),
        "decision": "limited_default_preflight_ready_broad_default_forbidden",
        "reason": (
            "Default flip is a product rollout, not compiler work. Limited cohort preflight is ready "
            "for explicit authorization; broad/system-wide default remains blocked until limited "
            "authorization, execution, soak review, and separate broad authorization."
        ),
    }


def _remote_ws_track(remote_ws_artifact_dir: str | Path | None) -> dict[str, Any]:
    if not remote_ws_artifact_dir:
        return {
            "status": "PENDING",
            "artifact_path": "",
            "remote_or_production_ws_turn_exercised": False,
            "reason": "remote_ws_artifact_missing_or_auth_not_configured",
            "required_scope": "QA cohort only over /api/v1/ws; no canonical learner truth write",
            "write_boundary": "remote runtime readback may be observed; published registry and canonical truth remain untouched",
        }
    root = Path(remote_ws_artifact_dir)
    manifest = _read_json(root / "manifest.json")
    go_no_go = _read_json(root / "go_no_go.json")
    strong = go_no_go.get("status") == "REMOTE_TEST2_WS_GO"
    stage_chain = list(manifest.get("stage_chain") or [])
    exercised = bool(manifest.get("remote_or_production_ws_turn_exercised")) or "remote_api_ws" in stage_chain
    if strong:
        status = "STRONG-GO"
    elif not exercised and go_no_go.get("status") == "REMOTE_WS_AUTH_MATERIAL_MISSING":
        status = "PENDING"
    else:
        status = "NO-GO"
    return {
        "status": status,
        "artifact_path": _rel(root),
        "remote_or_production_ws_turn_exercised": exercised,
        "entry": manifest.get("entry"),
        "api_base_url": manifest.get("api_base_url"),
        "ws_url": manifest.get("ws_url"),
        "evidence_scope": manifest.get("evidence_scope"),
        "cohort_user_id": manifest.get("cohort_user_id"),
        "cohort_identity": manifest.get("cohort_identity"),
        "stage_chain": stage_chain,
        "go_no_go_status": go_no_go.get("status"),
        "ws_grading_ok": bool(go_no_go.get("ws_grading_ok")),
        "same_projection_hash": bool(go_no_go.get("same_projection_hash")),
        "learning_brain_projection_hash": go_no_go.get("learning_brain_projection_hash"),
        "learning_report_projection_hash": go_no_go.get("learning_report_projection_hash"),
        "initial_has_construction_grading_result": bool(
            go_no_go.get("initial_has_construction_grading_result")
        ),
        "retest_has_construction_grading_result": bool(
            go_no_go.get("retest_has_construction_grading_result")
        ),
        "remote_runtime_state_observed": bool(go_no_go.get("remote_write_performed")),
        "canonical_truth_written": False,
        "published_registry_written": False,
        "production_db_write_performed": False,
        "note": (
            "The remote WS turn is evidence over a QA cohort runtime path. It is not a registry publish, "
            "not canonical learner truth promotion, and not a system-wide default flip."
        ),
    }


def _forbidden_actions(canonical: dict[str, Any], default_flip: dict[str, Any]) -> list[str]:
    actions = [
        "production_db_write",
        "canonical_learner_truth_write",
        "published_registry_write",
        "remote_or_aliyun_write",
        "system_wide_default_flip",
        "gpt55_or_claude_api_runtime_arm",
        "human_or_governance_release_signature",
    ]
    if canonical["status"] != "PREFLIGHT_READY_NOT_EXECUTED":
        actions.append("canonical_learner_truth_release_gate")
    if default_flip["broad_default"]["status"] != "PREFLIGHT_READY_NOT_EXECUTED":
        actions.append("broad_or_system_wide_default_gate")
    return actions


def build_r6_release_decision_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    decision_package_path: str | Path = P5_DECISION,
    cached_ab_report_path: str | Path = CACHED_AB,
    p5_package_path: str | Path = P5_PACKAGE,
    published_registry_preflight_path: str | Path = G3_PUBLISHED_REGISTRY,
    canonical_truth_preflight_path: str | Path = G4_CANONICAL_TRUTH,
    limited_default_preflight_path: str | Path = G1_LIMITED_DEFAULT,
    broad_default_preflight_path: str | Path = G2_BROAD_DEFAULT,
    remote_ws_artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    decision = _read_json(decision_package_path)
    cached_ab = _read_json(cached_ab_report_path)
    p5_package = _read_json(p5_package_path)
    registry_gate = _read_json(published_registry_preflight_path)
    canonical_gate = _read_json(canonical_truth_preflight_path)
    limited_default = _read_json(limited_default_preflight_path)
    broad_default = _read_json(broad_default_preflight_path)

    p1_to_p5 = dict(decision.get("overall") or {})
    cached_ab_track = _cached_ab_track(cached_ab)
    p5_track = _p5_track(p5_package)
    registry_track = _gate_track(registry_gate, artifact_path=Path(published_registry_preflight_path))
    canonical_track = _gate_track(canonical_gate, artifact_path=Path(canonical_truth_preflight_path))
    default_track = _system_wide_default_track(limited_default, broad_default)
    remote_track = _remote_ws_track(remote_ws_artifact_dir)

    phase_values = [
        p1_to_p5.get("phase1_nexus_like_scoring"),
        p1_to_p5.get("phase2_grading_to_brain_loop"),
        p1_to_p5.get("phase3_api_readback"),
        p1_to_p5.get("phase4_ws_readback"),
        p1_to_p5.get("phase5_real_wechat_package_readback"),
    ]
    p1_to_p5_strong = all(value == "STRONG-GO" for value in phase_values)
    remote_strong = remote_track["status"] == "STRONG-GO"
    release_gate_entry_allowed = p1_to_p5_strong and remote_strong
    forbidden = _forbidden_actions(canonical_track, default_track)
    not_exercised = list(decision.get("not_exercised") or [])
    if p5_track["status"] == "STRONG-GO" and "real_wechat_package_readback" in not_exercised:
        not_exercised.remove("real_wechat_package_readback")
    if remote_strong and "remote_or_production_ws_turn" in not_exercised:
        not_exercised.remove("remote_or_production_ws_turn")
    if not remote_strong and "remote_or_production_ws_turn" not in not_exercised:
        not_exercised.append("remote_or_production_ws_turn")

    package = {
        "schema_version": "luban_r6_release_decision_package.v1",
        "generated_at": "2026-06-12",
        "overall": {
            "verdict": "RELEASE_GATE_REVIEW_READY_WRITES_FORBIDDEN"
            if release_gate_entry_allowed
            else "NO-GO_REMOTE_WS_PENDING",
            "release_gate_entry_allowed": release_gate_entry_allowed,
            "write_actions_allowed": False,
            "quality_claim_allowed": False,
            "official_score_allowed": False,
            "is_release_truth": False,
            "reason": (
                "P1-P5 and remote /api/v1/ws are sufficient for release gate review, but publish, "
                "canonical learner truth, production DB, and default flip actions remain forbidden"
                if release_gate_entry_allowed
                else "P1-P5 are strong locally/real-WeChat, but remote_or_production_ws_turn is still pending"
            ),
        },
        "evidence": {
            "p1_to_p5": {
                "artifact_path": _rel(decision_package_path),
                "phase1_nexus_like_scoring": p1_to_p5.get("phase1_nexus_like_scoring"),
                "phase1_scope": p1_to_p5.get("phase1_scope"),
                "phase1_full_set_verdict": p1_to_p5.get("phase1_full_set_verdict"),
                "phase2_grading_to_brain_loop": p1_to_p5.get("phase2_grading_to_brain_loop"),
                "phase2_scope": p1_to_p5.get("phase2_scope"),
                "phase3_api_readback": p1_to_p5.get("phase3_api_readback"),
                "phase3_scope": p1_to_p5.get("phase3_scope"),
                "phase4_ws_readback": p1_to_p5.get("phase4_ws_readback"),
                "phase4_scope": p1_to_p5.get("phase4_scope"),
                "phase5_real_wechat_package_readback": p1_to_p5.get(
                    "phase5_real_wechat_package_readback"
                ),
                "phase5_scope": p1_to_p5.get("phase5_scope"),
                "release_verdict": p1_to_p5.get("release_verdict"),
            },
            "cached_ab": cached_ab_track,
            "real_wechat_package": p5_track,
        },
        "remote_or_production_ws_turn": remote_track,
        "preflights": {
            "published_registry": registry_track,
            "canonical_learner_truth_write": canonical_track,
            "system_wide_default_flip": default_track,
        },
        "release_gate": {
            "can_enter_as_evidence": [
                "p1_governed_subset_scoring",
                "p2_local_live_readback",
                "p3_local_api_readback",
                "p4_local_ws_readback",
                "p5_real_wechat_package_readback",
                "cached_ab_directional_effectiveness",
                "published_registry_preflight",
            ],
            "conditional_evidence_pending": []
            if remote_strong
            else ["remote_or_production_ws_turn"],
            "forbidden_actions": forbidden,
            "publish_preflight_result": registry_track["status"],
            "canonical_truth_preflight_result": canonical_track["status"],
            "default_flip_preflight_result": default_track["status"],
        },
        "not_exercised": not_exercised,
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_or_aliyun_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "system_wide_default_flipped": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
        "next_step": (
            "Run remote_or_production_ws_turn with QA cohort credentials, then rebuild this R6 package."
            if not remote_strong
            else "Ask for explicit human authorization before any registry publish, canonical truth write, or default flip."
        ),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "r6_release_decision_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--decision-package-path", default=str(P5_DECISION))
    parser.add_argument("--cached-ab-report-path", default=str(CACHED_AB))
    parser.add_argument("--p5-package-path", default=str(P5_PACKAGE))
    parser.add_argument("--published-registry-preflight-path", default=str(G3_PUBLISHED_REGISTRY))
    parser.add_argument("--canonical-truth-preflight-path", default=str(G4_CANONICAL_TRUTH))
    parser.add_argument("--limited-default-preflight-path", default=str(G1_LIMITED_DEFAULT))
    parser.add_argument("--broad-default-preflight-path", default=str(G2_BROAD_DEFAULT))
    parser.add_argument("--remote-ws-artifact-dir", default="")
    args = parser.parse_args()
    package = build_r6_release_decision_package(
        output_dir=args.output_dir,
        decision_package_path=args.decision_package_path,
        cached_ab_report_path=args.cached_ab_report_path,
        p5_package_path=args.p5_package_path,
        published_registry_preflight_path=args.published_registry_preflight_path,
        canonical_truth_preflight_path=args.canonical_truth_preflight_path,
        limited_default_preflight_path=args.limited_default_preflight_path,
        broad_default_preflight_path=args.broad_default_preflight_path,
        remote_ws_artifact_dir=args.remote_ws_artifact_dir or None,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0 if package["overall"]["release_gate_entry_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
