from __future__ import annotations

import json
from pathlib import Path


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "summary": {
            "original_v2_unit_count": 2,
            "original_unit_accounted_count": 2,
            "leaf_scoped_runtime_unit_count": 1,
            "non_runtime_excluded_or_gap_count": 1,
            "taxonomy_gap_candidate_count": 1,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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


def _near_live_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_near_live_shadow_ab.v1",
        "verdict": "PASS_V23_NEAR_LIVE_SHADOW_AB",
        "summary": {
            "case_count": 1,
            "provider_call_count": 0,
            "live_runtime_executed": False,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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


def _bridge() -> dict:
    return {
        "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "verdict": "PASS",
        "summary": {
            "candidate_event_count": 1,
            "learner_memory_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
        },
    }


def _projection() -> dict:
    return {
        "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "verdict": "PASS",
        "summary": {
            "top_claim_candidate_count": 1,
            "next_action_candidate_count": 1,
            "learner_memory_write_count": 0,
            "pcp_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "learner_memory_write_allowed": False,
            "personalization_context_pack_readback_allowed": False,
            "next_best_action_write_allowed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _sandbox_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "verdict": "PASS",
        "summary": {
            "candidate_event_count": 1,
            "sandbox_event_write_count": 1,
            "sandbox_readback_event_count": 1,
            "synthesis_observed_candidate_count": 0,
            "synthesis_compiled_object_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "learner_memory_write_allowed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _live_provider_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_live_provider_shadow_ab.v1",
        "verdict": "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB",
        "summary": {
            "sample_count": 1,
            "provider_call_count": 4,
            "total_tokens": 100,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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


def _live_residual_work_orders() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_live_residual_work_orders.v1",
        "verdict": "PASS_LIVE_RESIDUAL_WORK_ORDERS_READY",
        "summary": {
            "work_order_count": 1,
            "production_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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


def test_v23_learning_brain_candidate_closure_keeps_truth_and_writes_off() -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (
        build_v23_learning_brain_candidate_closure,
    )

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        bridge=_bridge(),
        projection=_projection(),
        sandbox_gate=_sandbox_gate(),
    )

    assert report["schema"] == "luban_rich_leaf_v23_learning_brain_candidate_closure.v1"
    assert report["verdict"] == "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
    assert report["quality_claim_allowed"] is False
    assert report["summary"]["candidate_event_count"] == 1
    assert report["summary"]["sandbox_readback_event_count"] == 1
    assert report["summary"]["learner_memory_write_count"] == 0
    assert report["summary"]["production_write_count"] == 0
    assert report["claim_scope"]["canonical_learner_truth_allowed"] is False
    assert report["safety"]["canonical_learner_truth_written"] is False
    assert "canonical_learner_truth_write" in report["not_exercised"]
    assert "live_provider_v23_four_arm_ab" in report["not_exercised"]


def test_v23_learning_brain_candidate_closure_accepts_live_provider_and_residual_evidence() -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (
        build_v23_learning_brain_candidate_closure,
    )

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        bridge=_bridge(),
        projection=_projection(),
        sandbox_gate=_sandbox_gate(),
        live_provider_ab=_live_provider_ab(),
        live_residual_work_orders=_live_residual_work_orders(),
    )

    assert report["verdict"] == "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
    assert report["claim_scope"]["live_provider_v23_sample_exercised"] is True
    assert report["claim_scope"]["compiler_feedback_work_orders_ready"] is True
    assert report["summary"]["live_provider_call_count"] == 4
    assert report["summary"]["live_residual_work_order_count"] == 1
    assert "live_provider_v23_four_arm_ab" not in report["not_exercised"]
    assert "compiler_feedback_from_live_residuals" not in report["not_exercised"]


def test_v23_learning_brain_candidate_closure_fails_on_sandbox_readback_mismatch() -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (
        build_v23_learning_brain_candidate_closure,
    )

    sandbox = _sandbox_gate()
    sandbox["summary"]["sandbox_readback_event_count"] = 0

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        bridge=_bridge(),
        projection=_projection(),
        sandbox_gate=sandbox,
    )

    assert report["verdict"] == "FAIL_SAFETY_OR_CONTRACT"
    assert "sandbox_readback_count_mismatch:0!=1" in report["blockers"]


def test_v23_learning_brain_candidate_closure_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import main

    runtime = tmp_path / "runtime.json"
    near_live = tmp_path / "near_live.json"
    bridge = tmp_path / "bridge.json"
    projection = tmp_path / "projection.json"
    sandbox = tmp_path / "sandbox.json"
    output = tmp_path / "closure.json"
    runtime.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")
    near_live.write_text(json.dumps(_near_live_ab(), ensure_ascii=False), encoding="utf-8")
    bridge.write_text(json.dumps(_bridge(), ensure_ascii=False), encoding="utf-8")
    projection.write_text(json.dumps(_projection(), ensure_ascii=False), encoding="utf-8")
    sandbox.write_text(json.dumps(_sandbox_gate(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--runtime-token-pack",
            str(runtime),
            "--near-live-ab",
            str(near_live),
            "--bridge",
            str(bridge),
            "--projection",
            str(projection),
            "--sandbox-gate",
            str(sandbox),
            "--live-provider-ab",
            str(tmp_path / "missing_live.json"),
            "--live-residual-work-orders",
            str(tmp_path / "missing_residuals.json"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_v23_learning_brain_candidate_closure.v1"
    assert payload["summary"]["blocker_count"] == 0


def test_v23_closure_requires_synthesis_to_observe_all_candidates_when_reported() -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (
        build_v23_learning_brain_candidate_closure,
    )

    sandbox = _sandbox_gate()
    sandbox["summary"]["synthesis_candidate_observation_count"] = 0  # silent drop

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        bridge=_bridge(),
        projection=_projection(),
        sandbox_gate=sandbox,
    )

    assert report["verdict"] == "FAIL_SAFETY_OR_CONTRACT"
    assert "synthesis_candidate_observation_count_mismatch:0!=1" in report["blockers"]


def test_v23_closure_surfaces_candidate_observation_count() -> None:
    from scripts.run_luban_rich_leaf_v23_learning_brain_candidate_closure import (
        build_v23_learning_brain_candidate_closure,
    )

    sandbox = _sandbox_gate()
    sandbox["summary"]["synthesis_candidate_observation_count"] = 1

    report = build_v23_learning_brain_candidate_closure(
        runtime_token_pack=_runtime_token_pack(),
        near_live_ab=_near_live_ab(),
        bridge=_bridge(),
        projection=_projection(),
        sandbox_gate=sandbox,
    )

    assert report["verdict"] == "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
    assert report["summary"]["synthesis_candidate_observation_count"] == 1
    # truth-leak invariants stay intact
    assert report["summary"]["synthesis_observed_candidate_count"] == 0
    assert report["summary"]["synthesis_compiled_object_count"] == 0
