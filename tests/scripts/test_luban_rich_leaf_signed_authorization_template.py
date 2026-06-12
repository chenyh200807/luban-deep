from __future__ import annotations

import json
from pathlib import Path


def _controlled_default_authorization() -> dict:
    return {
        "schema": "luban_rich_leaf_controlled_default_authorization_package.v1",
        "verdict": "READY_FOR_OPERATOR_SIGNATURE",
        "quality_claim_allowed": False,
        "authorization_decision": {
            "operator_signature_recorded": False,
            "controlled_default_authorized": False,
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "production_db_write_allowed": False,
            "remote_write_allowed": False,
            "release_truth_authorized": False,
        },
        "candidate_scope": {
            "runtime_token_pack_unit_count": 102,
            "supply_unit_count": 102,
            "streaming_sample_count": 16,
            "streaming_provider_call_count": 32,
            "streaming_ttft_delta_ms": -43.57,
        },
        "summary": {
            "blocker_count": 0,
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
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
            "remote_write_count": 0,
        },
    }


def _writeback_authorization_package() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
        "verdict": "READY_FOR_USER_AUTHORIZATION_DECISION",
        "quality_claim_allowed": False,
        "authorization_decision": {
            "explicit_user_authorization_required": True,
            "user_authorization_recorded": False,
            "test_learner_writeback_authorized": False,
            "canonical_truth_authorized": False,
            "production_db_authorized": False,
        },
        "candidate_scope": {
            "target_memory_kind": "learning_evidence",
            "target_source_feature": "rich_leaf_authorized_test_writeback",
            "target_user_scope": "test_learner_only_after_explicit_authorization",
            "max_candidate_event_count": 274,
            "top_claim_candidate_count": 274,
            "next_action_candidate_count": 3,
        },
        "summary": {
            "blocker_count": 0,
            "candidate_event_count": 274,
            "writeback_executed": False,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
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
        },
    }


def _release_governance_review() -> dict:
    return {
        "schema": "luban_rich_leaf_release_governance_review_packet.v1",
        "verdict": "BLOCKED_FOR_RELEASE_TRUTH",
        "quality_claim_allowed": False,
        "release_decision": {
            "release_truth_claim_allowed": False,
            "official_score_allowed": False,
            "production_default_allowed": False,
            "canonical_truth_write_allowed": False,
            "production_db_write_allowed": False,
            "requires_final_governance_signoff": True,
        },
        "summary": {
            "release_blocker_count": 4,
            "safety_violation_count": 0,
            "semantic_decision_count": 3506,
            "runtime_token_pack_unit_count": 102,
            "planned_learning_event_count": 274,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
        },
        "release_blockers": [
            "operator_signature_missing",
            "controlled_default_authorization_missing",
            "release_truth_authorization_missing",
            "learning_brain_signed_authorization_missing",
        ],
        "safety_violations": [],
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
        },
    }


def test_signed_authorization_template_is_unsigned_and_no_write() -> None:
    from scripts.run_luban_rich_leaf_signed_authorization_template import (
        run_signed_authorization_template,
    )

    report = run_signed_authorization_template(
        controlled_default_authorization=_controlled_default_authorization(),
        test_learner_writeback_authorization=_writeback_authorization_package(),
        release_governance_review=_release_governance_review(),
    )

    assert report["schema"] == "luban_rich_leaf_signed_authorization_template.v1"
    assert report["verdict"] == "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE"
    assert report["quality_claim_allowed"] is False
    assert report["summary"]["template_count"] == 3
    assert report["summary"]["write_executed"] is False
    assert report["summary"]["production_write_count"] == 0
    assert report["summary"]["learner_memory_write_count"] == 0

    runtime_template = report["signature_templates"]["controlled_default_operator"]
    assert runtime_template["signature_status"] == "unsigned"
    assert runtime_template["runtime_default_install_allowed"] is False
    assert runtime_template["canonical_pointer_write_allowed"] is False
    assert runtime_template["production_db_write_allowed"] is False
    assert runtime_template["remote_write_allowed"] is False
    assert runtime_template["release_truth_allowed"] is False
    assert runtime_template["required_evidence"]["runtime_token_pack_unit_count"] == 102

    writeback_template = report["signature_templates"]["test_learner_writeback"]
    assert writeback_template["signature_status"] == "unsigned"
    assert writeback_template["writeback_allowed"] is False
    assert writeback_template["target_user_id"] == "UNBOUND_SIGNED_AUTHORIZATION_REQUIRED"
    assert writeback_template["candidate_event_count"] == 274
    assert writeback_template["canonical_learner_truth_allowed"] is False

    release_template = report["signature_templates"]["release_truth_governance"]
    assert release_template["signature_status"] == "unsigned"
    assert release_template["release_truth_claim_allowed"] is False
    assert release_template["official_score_allowed"] is False
    assert release_template["requires_final_governance_signoff"] is True

    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["production_default"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["safety"]["learner_memory_write_count"] == 0


def test_signed_authorization_template_blocks_on_bad_input_shape() -> None:
    from scripts.run_luban_rich_leaf_signed_authorization_template import (
        run_signed_authorization_template,
    )

    controlled = _controlled_default_authorization()
    controlled["authorization_decision"]["default_install_allowed"] = True

    report = run_signed_authorization_template(
        controlled_default_authorization=controlled,
        test_learner_writeback_authorization=_writeback_authorization_package(),
        release_governance_review=_release_governance_review(),
    )

    assert report["verdict"] == "BLOCKED_INPUT_SAFETY_INVARIANT"
    assert "controlled_default_authorization:default_install_allowed_true" in report["blockers"]
    assert report["summary"]["write_executed"] is False
    assert report["classification"]["runtime_install_allowed"] is False


def test_signed_authorization_template_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_signed_authorization_template import main

    controlled = tmp_path / "controlled.json"
    writeback = tmp_path / "writeback.json"
    release = tmp_path / "release.json"
    output = tmp_path / "signed_authorization_template.json"
    controlled.write_text(json.dumps(_controlled_default_authorization(), ensure_ascii=False), encoding="utf-8")
    writeback.write_text(json.dumps(_writeback_authorization_package(), ensure_ascii=False), encoding="utf-8")
    release.write_text(json.dumps(_release_governance_review(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--controlled-default-authorization",
            str(controlled),
            "--test-learner-writeback-authorization",
            str(writeback),
            "--release-governance-review",
            str(release),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE"
    assert payload["summary"]["template_count"] == 3
