from __future__ import annotations

import json
from pathlib import Path


def _learning_evidence_candidate_bridge() -> dict:
    return {
        "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "input_schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "candidate_bridge",
        "summary": {
            "blocker_count": 0,
            "source_shadow_case_count": 1,
            "local_adapter_row_count": 1,
            "candidate_event_count": 1,
            "learner_memory_write_count": 0,
            "provider_call_count": 0,
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


def test_projection_builds_candidate_pcp_and_next_action_without_readback_or_truth() -> None:
    from scripts.run_luban_rich_leaf_pcp_nba_candidate_projection import run_pcp_nba_candidate_projection

    report = run_pcp_nba_candidate_projection(learning_evidence_candidate_bridge=_learning_evidence_candidate_bridge())

    assert report["schema"] == "luban_rich_leaf_pcp_nba_candidate_projection.v1"
    assert report["input_schema"] == "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
    assert report["verdict"] == "PASS"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "dry_run_candidate_projection"
    assert report["summary"]["candidate_event_count"] == 1
    assert report["summary"]["top_claim_candidate_count"] == 1
    assert report["summary"]["next_action_candidate_count"] == 1
    assert report["summary"]["learner_memory_write_count"] == 0
    assert report["summary"]["pcp_readback_count"] == 0

    pcp = report["personalization_context_pack_candidate"]
    assert pcp["source"] == "PersonalizationContextPackCandidate"
    assert pcp["candidate_only"] is True
    assert pcp["readback_verified"] is False
    assert pcp["authority"] == {
        "evidence": "learning_evidence_candidate_bridge",
        "claims": "candidate_projection_not_learning_synthesis",
        "prescription": "not_exercised_training_intent",
    }
    claim = pcp["top_claim_candidates"][0]
    assert claim["claim_status"] == "candidate_preview"
    assert claim["truth_eligible"] is False
    assert claim["evidence_refs"] == ["rich_leaf_le_candidate_1"]

    action = report["next_action_candidates"][0]
    assert action["candidate_only"] is True
    assert action["source"] == "rich_leaf_pcp_nba_candidate_projection"
    assert action["prescription_authority"] == "not_exercised_training_intent"
    assert action["status"] == "candidate_not_prescription"
    assert action["evidence_refs"] == ["rich_leaf_le_candidate_1"]
    assert "training_intent_creation" in report["not_exercised_by_layer"]["learning_brain_not_exercised"]
    assert report["safety"]["canonical_learner_truth_written"] is False


def test_projection_blocks_writeback_eligible_candidate_events() -> None:
    from scripts.run_luban_rich_leaf_pcp_nba_candidate_projection import run_pcp_nba_candidate_projection

    bridge = _learning_evidence_candidate_bridge()
    bridge["learning_evidence_event_candidates"][0]["quality"]["writeback_eligible"] = True

    report = run_pcp_nba_candidate_projection(learning_evidence_candidate_bridge=bridge)

    assert report["verdict"] == "FAIL"
    assert "candidate_event_quality_writeback_eligible:rich_leaf_le_candidate_1" in report["blockers"]
    assert report["summary"]["top_claim_candidate_count"] == 0


def test_projection_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_pcp_nba_candidate_projection import main

    bridge = tmp_path / "learning_evidence_candidate_bridge.json"
    output = tmp_path / "pcp_nba_candidate_projection.json"
    bridge.write_text(json.dumps(_learning_evidence_candidate_bridge(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--learning-evidence-candidate-bridge", str(bridge), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_pcp_nba_candidate_projection.v1"
    assert payload["safety"]["next_best_action_write_count"] == 0
