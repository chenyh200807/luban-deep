from __future__ import annotations

import json
from pathlib import Path


def _sandbox_gate(sandbox_events_path: str = "") -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "verdict": "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "artifact_only_sandbox_readback",
        "sandbox": {
            "sandbox_user_id": "rich_leaf_sandbox_learner",
            "sandbox_events_path": sandbox_events_path,
            "write_scope": "artifact_only",
        },
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "valid_candidate_event_count": 2,
            "sandbox_event_write_count": 2,
            "sandbox_readback_event_count": 2,
            "synthesis_observed_candidate_count": 0,
            "synthesis_compiled_object_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_sandbox_readback_gate": True,
            "sandbox_write_scope": "artifact_only",
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
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _authorization_package() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
        "input_schemas": {
            "authorized_writeback_preflight": "luban_rich_leaf_authorized_writeback_preflight.v1",
        },
        "verdict": "READY_FOR_USER_AUTHORIZATION_DECISION",
        "quality_claim_allowed": False,
        "execution_mode": "authorization_package_only",
        "authorization_decision": {
            "explicit_user_authorization_required": True,
            "user_authorization_recorded": False,
            "test_learner_writeback_authorized": False,
            "allowed_write_scope": "none_without_signed_authorization",
            "canonical_truth_authorized": False,
            "production_db_authorized": False,
        },
        "candidate_scope": {
            "target_memory_kind": "learning_evidence",
            "target_source_feature": "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
            "max_candidate_event_count": 2,
            "top_claim_candidate_count": 2,
            "next_action_candidate_count": 1,
        },
        "rollback_plan": {
            "plan_status": "draft_review_required",
            "pre_write_snapshot_required": True,
            "delete_by_source_feature_required": True,
            "rollback_artifacts": [
                "pre_write_learner_memory_snapshot",
                "write_batch_manifest",
                "post_write_readback_report",
            ],
        },
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 2,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "provider_call_count": 0,
        },
        "missing_authorizations": [
            "signed_user_authorization_record",
            "concrete_test_learner_id",
            "teacher_final_or_governance_review",
            "approved_rollback_plan",
            "separate_canonical_truth_authorization",
        ],
        "blockers": [],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "test_learner_writeback_authorization_package": True,
            "test_learner_writeback_allowed": False,
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
            "personalization_context_pack_readback_count": 0,
            "training_intent_write_count": 0,
            "next_best_action_write_count": 0,
        },
    }


def _sandbox_rows() -> list[dict]:
    rows = []
    for idx in range(2):
        event_id = f"rich_leaf_le_candidate_{idx + 1}"
        rows.append(
            {
                "event_id": event_id,
                "user_id": "rich_leaf_sandbox_learner",
                "source_feature": "rich_leaf_shadow_candidate",
                "source_id": f"near_live_shadow_{idx + 1:04d}",
                "source_bot_id": "construction-exam-sandbox",
                "memory_kind": "learning_evidence",
                "dedupe_key": f"rich_leaf_sandbox_dedupe_{idx + 1}",
                "created_at": "2026-06-12T00:00:00+08:00",
                "payload_json": {
                    "candidate_event_id": event_id,
                    "event_type": "learning_evidence",
                    "memory_kind": "learning_evidence",
                    "candidate_only": True,
                    "preview_only": True,
                    "claim_promotion_allowed": False,
                    "canonical_truth_written": False,
                    "question_id": f"near_live_shadow_{idx + 1:04d}",
                    "quality": {
                        "writeback_eligible": False,
                        "progress_countable": False,
                        "truth_eligible": False,
                        "stable_truth_eligible": False,
                    },
                    "rich_leaf_trace": {
                        "leaf_id": f"L{idx + 1}",
                        "artifact_id": f"A{idx + 1}",
                        "field_id": f"F{idx + 1}",
                        "task": "rag_answer",
                    },
                },
            }
        )
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_dry_run_manifest_builds_idempotent_write_candidates_without_writing(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_dry_run_manifest import (
        run_test_learner_writeback_dry_run_manifest,
    )

    sandbox_events = tmp_path / "sandbox_memory_events.jsonl"
    _write_jsonl(sandbox_events, _sandbox_rows())
    sandbox = _sandbox_gate(str(sandbox_events))

    report = run_test_learner_writeback_dry_run_manifest(
        test_learner_sandbox_readback_gate=sandbox,
        test_learner_writeback_authorization_package=_authorization_package(),
        sandbox_events=sandbox_events,
    )

    assert report["schema"] == "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1"
    assert report["verdict"] == "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "dry_run_manifest_only"
    assert report["target_scope"]["target_user_id"] == "not_bound_without_authorization"
    assert report["target_scope"]["target_source_feature"] == "rich_leaf_authorized_test_writeback"
    assert report["write_batch_candidate"]["event_count"] == 2
    assert report["write_batch_candidate"]["idempotency_key_count"] == 2
    assert report["rollback_selector"]["source_feature"] == "rich_leaf_authorized_test_writeback"
    assert report["summary"]["writeback_executed"] is False
    assert report["summary"]["learner_memory_write_count"] == 0
    assert len(report["event_write_candidates"]) == 2
    first = report["event_write_candidates"][0]
    assert first["target_user_id"] == "not_bound_without_authorization"
    assert first["write_allowed"] is False
    assert first["source_feature"] == "rich_leaf_authorized_test_writeback"
    assert first["payload_json"]["quality"]["writeback_eligible"] is False
    assert report["classification"]["learner_memory_write_allowed"] is False
    assert report["safety"]["canonical_learner_truth_written"] is False


def test_dry_run_manifest_blocks_authorization_or_count_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_dry_run_manifest import (
        run_test_learner_writeback_dry_run_manifest,
    )

    sandbox_events = tmp_path / "sandbox_memory_events.jsonl"
    _write_jsonl(sandbox_events, _sandbox_rows())
    package = _authorization_package()
    package["authorization_decision"]["user_authorization_recorded"] = True
    package["candidate_scope"]["max_candidate_event_count"] = 99

    report = run_test_learner_writeback_dry_run_manifest(
        test_learner_sandbox_readback_gate=_sandbox_gate(str(sandbox_events)),
        test_learner_writeback_authorization_package=package,
        sandbox_events=sandbox_events,
    )

    assert report["verdict"] == "FAIL"
    assert "authorization_package_user_authorization_recorded" in report["blockers"]
    assert "authorization_package_candidate_count_drift" in report["blockers"]
    assert report["summary"]["writeback_executed"] is False


def test_dry_run_manifest_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_test_learner_writeback_dry_run_manifest import main

    sandbox_events = tmp_path / "sandbox_memory_events.jsonl"
    sandbox_gate = tmp_path / "test_learner_sandbox_readback_gate.json"
    authorization_package = tmp_path / "test_learner_writeback_authorization_package.json"
    output = tmp_path / "test_learner_writeback_dry_run_manifest.json"
    _write_jsonl(sandbox_events, _sandbox_rows())
    sandbox_gate.write_text(json.dumps(_sandbox_gate(str(sandbox_events)), ensure_ascii=False), encoding="utf-8")
    authorization_package.write_text(json.dumps(_authorization_package(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--test-learner-sandbox-readback-gate",
            str(sandbox_gate),
            "--test-learner-writeback-authorization-package",
            str(authorization_package),
            "--sandbox-events",
            str(sandbox_events),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1"
    assert payload["write_batch_candidate"]["event_count"] == 2
