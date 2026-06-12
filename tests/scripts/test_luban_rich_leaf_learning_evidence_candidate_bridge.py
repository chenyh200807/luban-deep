from __future__ import annotations

import json
from pathlib import Path


def _near_live_shadow_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
        "verdict": "PASS",
        "verdict_ceiling": "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY",
        "quality_claim_allowed": False,
        "execution_mode": "near_live_shadow",
        "summary": {
            "blocker_count": 0,
            "shadow_case_count": 1,
            "provider_call_count": 0,
            "local_adapter_fail_open_rate": 0.0,
            "local_adapter_question_lane_citation_rate": 0.0,
        },
        "local_adapter_rows": [
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": "near_live_shadow_0001",
                "task": "rag_answer",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "field_id": "rule_1",
                "family": "rules",
                "answerable": True,
                "term_hit": True,
                "fail_open": False,
                "citation_count": 1,
                "question_lane_citation_count": 0,
                "cited_source_ref_ids": ["src_target"],
                "expected_source_ref_ids": ["src_target"],
                "answer": {
                    "text": "建筑设计一般可分为四个阶段",
                    "cited_source_ref_ids": ["src_target"],
                },
            }
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_near_live_shadow_ab": True,
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


def _v23_near_live_shadow_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_near_live_shadow_ab.v1",
        "verdict": "PASS_V23_NEAR_LIVE_SHADOW_AB",
        "verdict_ceiling": "NEAR_LIVE_PROXY_ONLY",
        "quality_claim_allowed": False,
        "summary": {
            "arm_count": 4,
            "blocker_count": 0,
            "case_count": 1,
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "rows": [
            {
                "arm": "current_rag_proxy",
                "case_id": "v23_shadow_0001",
                "leaf_id": "L1",
                "answerable": False,
                "matches_expected": False,
                "evidence_cited": False,
                "fail_open": True,
            },
            {
                "arm": "rich_leaf_v23_context",
                "case_id": "v23_shadow_0001",
                "leaf_id": "L1",
                "answerable": True,
                "matches_expected": True,
                "evidence_cited": True,
                "fail_open": False,
                "token_proxy": 100,
            },
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "v23_near_live_shadow_ab": True,
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


def _runtime_token_pack_v23() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "summary": {
            "leaf_scoped_runtime_unit_count": 1,
            "production_write_count": 0,
            "runtime_install_count": 0,
        },
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp23_1",
                "leaf_id": "L1",
                "leaf_name_path": "root > leaf",
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "compiled_context": {
                    "definitions": ["定义 A"],
                    "rules": ["规则 A"],
                    "procedures": ["步骤 A"],
                },
                "source_ref": {
                    "source_path": "2026教材/a.json",
                    "record_id": "2026教材/a.json",
                    "source_lane": "textbook",
                    "span_hash": "span123",
                    "file_sha256": "file123",
                },
            }
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack_v23": True,
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


def test_candidate_bridge_projects_shadow_rows_to_review_only_learning_evidence() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_candidate_bridge import run_learning_evidence_candidate_bridge

    report = run_learning_evidence_candidate_bridge(near_live_shadow_ab=_near_live_shadow_ab())

    assert report["schema"] == "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
    assert report["input_schema"] == "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["quality_claim_allowed"] is False
    assert report["classification"] == {
        "candidate_only": True,
        "review_only": True,
        "learning_evidence_candidate_bridge": True,
        "learner_memory_write_allowed": False,
        "runtime_install_allowed": False,
        "production_default": False,
        "release_truth_claimed": False,
    }
    assert report["safety"]["canonical_truth_written"] is False
    assert report["safety"]["learner_memory_write_count"] == 0
    assert report["summary"]["candidate_event_count"] == 1

    event = report["learning_evidence_event_candidates"][0]
    assert event["event_type"] == "learning_evidence"
    assert event["memory_kind"] == "learning_evidence"
    assert event["source_feature"] == "rich_leaf_shadow_candidate"
    assert event["candidate_only"] is True
    assert event["preview_only"] is True
    assert event["claim_promotion_allowed"] is False
    assert event["canonical_truth_written"] is False
    assert event["quality"]["writeback_eligible"] is False
    assert event["quality"]["candidate_only"] is True
    assert event["rich_leaf_trace"] == {
        "case_id": "near_live_shadow_0001",
        "task": "rag_answer",
        "artifact_id": "A1",
        "leaf_id": "L1",
        "field_id": "rule_1",
        "family": "rules",
        "cited_source_ref_ids": ["src_target"],
    }
    assert "learner_memory_db_write" in report["not_exercised_by_layer"]["memory_not_exercised"]
    assert "personalization_context_pack_readback" in report["not_exercised_by_layer"]["learning_brain_not_exercised"]


def test_candidate_bridge_projects_v23_runtime_pack_to_review_only_learning_evidence() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_candidate_bridge import run_learning_evidence_candidate_bridge

    report = run_learning_evidence_candidate_bridge(
        near_live_shadow_ab=_v23_near_live_shadow_ab(),
        runtime_token_pack_v23=_runtime_token_pack_v23(),
    )

    assert report["schema"] == "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
    assert report["input_schema"] == "luban_rich_leaf_v23_near_live_shadow_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["quality_claim_allowed"] is False
    assert report["summary"]["local_adapter_row_count"] == 1
    assert report["summary"]["candidate_event_count"] == 1
    assert report["safety"]["learner_memory_write_count"] == 0

    event = report["learning_evidence_event_candidates"][0]
    assert event["question_type"] == "rich_leaf_v23_shadow_runtime_case"
    assert event["candidate_only"] is True
    assert event["preview_only"] is True
    assert event["quality"]["writeback_eligible"] is False
    assert event["quality"]["truth_eligible"] is False
    assert event["rich_leaf_trace"] == {
        "case_id": "v23_shadow_0001",
        "task": "rich_leaf_v23_runtime_context",
        "artifact_id": "rtp23_1",
        "leaf_id": "L1",
        "field_id": "runtime_token_pack_v23",
        "family": "rich_leaf_runtime_token_pack",
        "cited_source_ref_ids": ["2026教材/a.json#span123"],
    }
    assert event["evidence_refs"][0]["ref"] == "2026教材/a.json#span123"
    assert event["evidence_refs"][0]["source_ref"]["source_lane"] == "textbook"
    assert event["canonical_truth_written"] is False


def test_candidate_bridge_blocks_v23_without_runtime_pack() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_candidate_bridge import run_learning_evidence_candidate_bridge

    report = run_learning_evidence_candidate_bridge(near_live_shadow_ab=_v23_near_live_shadow_ab())

    assert report["verdict"] == "FAIL"
    assert "v23_runtime_token_pack_missing" in report["blockers"]
    assert report["summary"]["candidate_event_count"] == 0


def test_candidate_bridge_blocks_shadow_rows_without_traceable_citations() -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_candidate_bridge import run_learning_evidence_candidate_bridge

    payload = _near_live_shadow_ab()
    payload["local_adapter_rows"][0]["cited_source_ref_ids"] = []

    report = run_learning_evidence_candidate_bridge(near_live_shadow_ab=payload)

    assert report["verdict"] == "FAIL"
    assert "candidate_row_without_cited_source_ref:near_live_shadow_0001" in report["blockers"]
    assert report["summary"]["candidate_event_count"] == 0


def test_candidate_bridge_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_learning_evidence_candidate_bridge import main

    shadow = tmp_path / "near_live_shadow_ab.json"
    output = tmp_path / "learning_evidence_candidate_bridge.json"
    shadow.write_text(json.dumps(_near_live_shadow_ab(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--near-live-shadow-ab", str(shadow), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
    assert payload["safety"]["learner_memory_write_count"] == 0
