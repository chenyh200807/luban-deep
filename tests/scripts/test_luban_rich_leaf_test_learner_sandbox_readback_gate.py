from __future__ import annotations

import json
from pathlib import Path


def _learning_evidence_candidate_bridge() -> dict:
    return {
        "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 1,
            "learner_memory_write_count": 0,
        },
        "learning_evidence_event_candidates": [
            {
                "event_type": "learning_evidence",
                "memory_kind": "learning_evidence",
                "source_feature": "rich_leaf_shadow_candidate",
                "candidate_event_id": "rich_leaf_le_candidate_1",
                "candidate_only": True,
                "preview_only": True,
                "claim_promotion_allowed": False,
                "mastery_raised": False,
                "canonical_truth_written": False,
                "question_id": "near_live_shadow_0001",
                "quality": {
                    "candidate_only": True,
                    "authority": "rich_leaf_shadow_candidate",
                    "writeback_eligible": False,
                    "progress_countable": False,
                    "truth_eligible": False,
                    "stable_truth_eligible": False,
                    "evidence_level": "preview_needs_retest",
                },
                "rich_leaf_trace": {
                    "case_id": "near_live_shadow_0001",
                    "task": "rag_answer",
                    "artifact_id": "A1",
                    "leaf_id": "L1",
                    "field_id": "rule_1",
                    "family": "rules",
                    "cited_source_ref_ids": ["src_target"],
                },
            }
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "learning_evidence_candidate_bridge": True,
            "learner_memory_write_allowed": False,
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


def _pcp_nba_projection() -> dict:
    return {
        "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "input_schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "dry_run_candidate_projection",
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 1,
            "valid_candidate_event_count": 1,
            "top_claim_candidate_count": 1,
            "next_action_candidate_count": 1,
            "learner_memory_write_count": 0,
            "pcp_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
            "provider_call_count": 0,
        },
        "personalization_context_pack_candidate": {
            "source": "PersonalizationContextPackCandidate",
            "candidate_only": True,
            "readback_verified": False,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "pcp_nba_candidate_projection": True,
            "learner_memory_write_allowed": False,
            "personalization_context_pack_readback_allowed": False,
            "next_best_action_write_allowed": False,
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
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def test_sandbox_gate_writes_artifact_only_events_and_filters_from_synthesis(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_sandbox_readback_gate import run_test_learner_sandbox_readback_gate

    sandbox_events = tmp_path / "sandbox_memory_events.jsonl"
    report = run_test_learner_sandbox_readback_gate(
        learning_evidence_candidate_bridge=_learning_evidence_candidate_bridge(),
        pcp_nba_candidate_projection=_pcp_nba_projection(),
        sandbox_events=sandbox_events,
    )

    assert report["schema"] == "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
    assert report["verdict"] == "PASS"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "artifact_only_sandbox_readback"
    assert report["summary"]["candidate_event_count"] == 1
    assert report["summary"]["sandbox_event_write_count"] == 1
    assert report["summary"]["sandbox_readback_event_count"] == 1
    assert report["summary"]["synthesis_observed_candidate_count"] == 0
    assert report["summary"]["synthesis_compiled_object_count"] == 0
    assert report["summary"]["learner_memory_write_count"] == 0
    assert report["classification"]["learner_memory_write_allowed"] is False
    assert report["classification"]["sandbox_write_scope"] == "artifact_only"
    assert report["safety"]["canonical_learner_truth_written"] is False
    assert report["safety"]["production_write_count"] == 0
    assert sandbox_events.exists()
    row = json.loads(sandbox_events.read_text(encoding="utf-8").splitlines()[0])
    assert row["memory_kind"] == "learning_evidence"
    assert row["payload_json"]["candidate_only"] is True
    assert row["payload_json"]["quality"]["writeback_eligible"] is False
    assert "learner_state_service_append_memory_event" in report["not_exercised_by_layer"]["memory_not_exercised"]


def test_sandbox_gate_blocks_projection_that_claims_pcp_readback() -> None:
    from scripts.run_luban_rich_leaf_test_learner_sandbox_readback_gate import run_test_learner_sandbox_readback_gate

    projection = _pcp_nba_projection()
    projection["summary"]["pcp_readback_count"] = 1

    report = run_test_learner_sandbox_readback_gate(
        learning_evidence_candidate_bridge=_learning_evidence_candidate_bridge(),
        pcp_nba_candidate_projection=projection,
    )

    assert report["verdict"] == "FAIL"
    assert "pcp_projection_summary_pcp_readback_count" in report["blockers"]
    assert report["summary"]["sandbox_event_write_count"] == 0


def test_sandbox_gate_cli_writes_report_and_sandbox_jsonl(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_sandbox_readback_gate import main

    bridge = tmp_path / "learning_evidence_candidate_bridge.json"
    projection = tmp_path / "pcp_nba_candidate_projection.json"
    output = tmp_path / "test_learner_sandbox_readback_gate.json"
    sandbox_events = tmp_path / "sandbox_memory_events.jsonl"
    bridge.write_text(json.dumps(_learning_evidence_candidate_bridge(), ensure_ascii=False), encoding="utf-8")
    projection.write_text(json.dumps(_pcp_nba_projection(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--learning-evidence-candidate-bridge",
            str(bridge),
            "--pcp-nba-candidate-projection",
            str(projection),
            "--sandbox-events",
            str(sandbox_events),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_test_learner_sandbox_readback_gate.v1"
    assert payload["summary"]["sandbox_readback_event_count"] == 1
    assert sandbox_events.exists()
