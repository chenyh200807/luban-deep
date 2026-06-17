from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _legacy_audit() -> dict:
    return {
        "schema": "luban_rich_leaf_legacy_compilation_quality_audit.v1",
        "verdict": "NO_GO_FOR_DIRECT_REUSE",
        "summary": {
            "artifact_dir_count": 9,
            "direct_reuse_blocked_count": 9,
            "quality_gap_count": 25,
            "safety_violation_count": 1,
        },
        "classification": {
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
        },
    }


def _decision_validation() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_decision_validation.v1",
        "verdict": "INCOMPLETE",
        "summary": {
            "audit_item_count": 3506,
            "decision_count": 3383,
            "missing_decision_count": 123,
            "invalid_decision_count": 0,
        },
        "classification": {
            "review_only": True,
            "decisions_recorded": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
    }


def _manual_packets() -> dict:
    return {
        "schema": "luban_rich_leaf_manual_review_packets.v1",
        "verdict": "PASS",
        "summary": {
            "manual_review_packet_count": 123,
            "decision_count": 0,
            "by_missing_lane": {"standard": 52, "textbook": 34, "lecture": 25, "question": 12},
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
        },
    }


def _live_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_live_ab.v1",
        "verdict": "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED",
        "summary": {
            "live_runtime_executed": False,
            "provider_call_count": 0,
            "live_case_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
        },
        "not_exercised": ["live_llm_semantic_judgment", "release_truth_governance"],
    }


def _writeback_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
        "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
        "summary": {
            "planned_event_count": 274,
            "dry_run_planned_event_count": 274,
            "learner_memory_write_count": 0,
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
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
            "canonical_learner_truth_written": False,
        },
    }


def _runtime_default_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_default_gate.v1",
        "verdict": "READY_FOR_CONTROLLED_DEFAULT_REVIEW",
        "summary": {
            "blocker_count": 0,
            "token_pack_unit_count": 102,
            "supply_unit_count": 102,
            "streaming_sample_count": 16,
            "streaming_provider_call_count": 32,
            "streaming_ttft_delta_ms": -43.57,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _controlled_default_authorization() -> dict:
    return {
        "schema": "luban_rich_leaf_controlled_default_authorization_package.v1",
        "verdict": "READY_FOR_OPERATOR_SIGNATURE",
        "authorization_decision": {
            "operator_signature_recorded": False,
            "controlled_default_authorized": False,
            "release_truth_authorized": False,
        },
        "summary": {
            "blocker_count": 0,
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
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
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
        },
    }


def _release_governance_review() -> dict:
    return {
        "schema": "luban_rich_leaf_release_governance_review_packet.v1",
        "verdict": "BLOCKED_FOR_RELEASE_TRUTH",
        "summary": {
            "release_blocker_count": 4,
            "safety_violation_count": 0,
            "production_write_count": 0,
            "learner_memory_write_count": 0,
        },
        "release_blockers": [
            "operator_signature_missing",
            "controlled_default_authorization_missing",
            "release_truth_authorization_missing",
            "learning_brain_signed_authorization_missing",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "production_write_count": 0,
            "release_truth_claimed": False,
            "installed_runtime_supply": False,
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "learner_memory_write_count": 0,
        },
    }


def _signed_authorization_template() -> dict:
    return {
        "schema": "luban_rich_leaf_signed_authorization_template.v1",
        "verdict": "READY_FOR_EXTERNAL_SIGNATURE_CAPTURE",
        "summary": {
            "template_count": 3,
            "blocker_count": 0,
            "candidate_event_count": 274,
            "planned_learning_event_count": 274,
            "write_executed": False,
            "runtime_default_install_count": 0,
            "canonical_pointer_write_count": 0,
            "learner_memory_write_count": 0,
            "canonical_truth_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "signed_authorization_template": True,
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
            "remote_write_count": 0,
        },
    }


def test_compiler_status_ledger_reports_shadow_candidate_not_release_truth() -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import build_compiler_status_ledger

    report = build_compiler_status_ledger(
        legacy_quality_audit=_legacy_audit(),
        decision_validation=_decision_validation(),
        manual_review_packets=_manual_packets(),
        semantic_runtime_live_ab=_live_ab(),
        writeback_execution_gate=_writeback_gate(),
    )

    assert report["schema"] == "luban_rich_leaf_compiler_status_ledger.v1"
    assert report["overall_verdict"] == "WEAK_GO_SHADOW_CANDIDATE"
    assert report["quality_claim_allowed"] is False
    assert report["runtime_default_status"] == "not_exercised"
    assert report["learning_brain_write_status"] == "blocked_pending_signed_authorization"
    assert report["release_truth_claimed"] is False
    assert report["summary"]["manual_review_packet_count"] == 123
    assert report["summary"]["missing_semantic_decision_count"] == 123
    assert report["summary"]["provider_call_count"] == 0
    assert report["stage_status"]["manual_review"]["status"] == "ready_for_ai_council_review"
    assert "manual_review_backlog:123" in report["blockers"]
    assert "live_provider_authorization_missing" in report["blockers"]
    assert "release_governance_not_exercised" in report["blockers"]
    assert "run_ai_council_manual_review_packets" in report["recommended_next_actions"]


def test_compiler_status_ledger_fails_closed_on_safety_invariant_drift() -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import build_compiler_status_ledger

    live_ab = _live_ab()
    live_ab["safety"]["production_write_count"] = 1
    manual_packets = _manual_packets()
    manual_packets["classification"]["release_truth_claimed"] = True

    report = build_compiler_status_ledger(
        legacy_quality_audit=_legacy_audit(),
        decision_validation=_decision_validation(),
        manual_review_packets=manual_packets,
        semantic_runtime_live_ab=live_ab,
        writeback_execution_gate=_writeback_gate(),
    )

    assert report["overall_verdict"] == "NO_GO_SAFETY_INVARIANT"
    assert report["quality_claim_allowed"] is False
    assert "manual_review_packets:classification.release_truth_claimed_not_false" in report["safety_violations"]
    assert "semantic_runtime_live_ab:safety.production_write_count_nonzero" in report["safety_violations"]


def test_compiler_status_ledger_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import main

    legacy = tmp_path / "legacy.json"
    decisions = tmp_path / "decisions.json"
    manual = tmp_path / "manual.json"
    live = tmp_path / "live.json"
    writeback = tmp_path / "writeback.json"
    output = tmp_path / "compiler_status_ledger.json"
    _write_json(legacy, _legacy_audit())
    _write_json(decisions, _decision_validation())
    _write_json(manual, _manual_packets())
    _write_json(live, _live_ab())
    _write_json(writeback, _writeback_gate())

    exit_code = main(
        [
            "--legacy-quality-audit",
            str(legacy),
            "--decision-validation",
            str(decisions),
            "--manual-review-packets",
            str(manual),
            "--semantic-runtime-live-ab",
            str(live),
            "--writeback-execution-gate",
            str(writeback),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["overall_verdict"] == "WEAK_GO_SHADOW_CANDIDATE"
    assert payload["summary"]["legacy_direct_reuse_blocked_count"] == 9


def test_compiler_status_ledger_reports_completed_manual_shadow_decisions() -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import build_compiler_status_ledger

    decisions = _decision_validation()
    decisions["verdict"] = "PASS"
    decisions["summary"]["decision_count"] = 3506
    decisions["summary"]["missing_decision_count"] = 0
    live_ab = _live_ab()
    live_ab["verdict"] = "PASS_LIVE_RUNTIME_AB_SHADOW"
    live_ab["summary"]["live_runtime_executed"] = True
    live_ab["summary"]["provider_call_count"] = 1096
    live_ab["not_exercised"] = ["production_default_decision", "release_truth_governance"]

    report = build_compiler_status_ledger(
        legacy_quality_audit=_legacy_audit(),
        decision_validation=decisions,
        manual_review_packets=_manual_packets(),
        semantic_runtime_live_ab=live_ab,
        writeback_execution_gate=_writeback_gate(),
        runtime_default_gate=_runtime_default_gate(),
    )

    assert report["overall_verdict"] == "WEAK_GO_SHADOW_CANDIDATE"
    assert report["summary"]["manual_review_packet_count"] == 123
    assert report["summary"]["missing_semantic_decision_count"] == 0
    assert report["runtime_default_status"] == "ready_for_controlled_default_review"
    assert report["stage_status"]["manual_review"]["status"] == "shadow_decisions_completed"


def test_compiler_status_ledger_reports_signed_template_without_unblocking_release() -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import build_compiler_status_ledger

    decisions = _decision_validation()
    decisions["verdict"] = "PASS"
    decisions["summary"]["decision_count"] = 3506
    decisions["summary"]["missing_decision_count"] = 0
    live_ab = _live_ab()
    live_ab["verdict"] = "PASS_LIVE_RUNTIME_AB_SHADOW"
    live_ab["summary"]["live_runtime_executed"] = True
    live_ab["summary"]["provider_call_count"] = 1096
    live_ab["not_exercised"] = ["production_default_decision"]

    report = build_compiler_status_ledger(
        legacy_quality_audit=_legacy_audit(),
        decision_validation=decisions,
        manual_review_packets=_manual_packets(),
        semantic_runtime_live_ab=live_ab,
        writeback_execution_gate=_writeback_gate(),
        runtime_default_gate=_runtime_default_gate(),
        controlled_default_authorization=_controlled_default_authorization(),
        release_governance_review=_release_governance_review(),
        signed_authorization_template=_signed_authorization_template(),
    )

    assert report["overall_verdict"] == "WEAK_GO_SHADOW_CANDIDATE"
    assert report["stage_status"]["signed_authorization_template"]["status"] == "ready_for_external_signature_capture"
    assert report["stage_status"]["signed_authorization_template"]["template_count"] == 3
    assert report["summary"]["signed_authorization_template_count"] == 3
    assert report["summary"]["production_write_count"] == 0
    assert "controlled_default_authorization_missing" in report["blockers"]
    assert "release_truth_authorization_missing" in report["blockers"]
    assert "learning_brain_signed_authorization_missing" in report["blockers"]
    assert report["safety"]["installed_runtime_supply"] is False
    assert report["safety"]["release_truth_claimed"] is False
    assert "manual_review_backlog:123" not in report["blockers"]
    assert "semantic_decisions_incomplete:123" not in report["blockers"]


def test_compiler_status_ledger_reports_exercised_release_governance_blockers() -> None:
    from scripts.run_luban_rich_leaf_compiler_status_ledger import build_compiler_status_ledger

    decisions = _decision_validation()
    decisions["verdict"] = "PASS"
    decisions["summary"]["decision_count"] = 3506
    decisions["summary"]["missing_decision_count"] = 0
    live_ab = _live_ab()
    live_ab["verdict"] = "PASS_LIVE_RUNTIME_AB_SHADOW"
    live_ab["summary"]["live_runtime_executed"] = True
    live_ab["summary"]["provider_call_count"] = 1096
    live_ab["not_exercised"] = ["production_default_decision", "release_truth_governance"]

    report = build_compiler_status_ledger(
        legacy_quality_audit=_legacy_audit(),
        decision_validation=decisions,
        manual_review_packets=_manual_packets(),
        semantic_runtime_live_ab=live_ab,
        writeback_execution_gate=_writeback_gate(),
        runtime_default_gate=_runtime_default_gate(),
        controlled_default_authorization=_controlled_default_authorization(),
        release_governance_review=_release_governance_review(),
    )

    assert report["overall_verdict"] == "WEAK_GO_SHADOW_CANDIDATE"
    assert report["stage_status"]["controlled_default_authorization"]["status"] == "ready_for_operator_signature"
    assert report["stage_status"]["release_governance"]["status"] == "blocked_for_release_truth"
    assert report["summary"]["release_governance_blocker_count"] == 4
    assert report["summary"]["blocker_count"] == 4
    assert len(report["blockers"]) == len(set(report["blockers"]))
    assert "release_governance_not_exercised" not in report["blockers"]
    assert "operator_signature_missing" in report["blockers"]
    assert "controlled_default_authorization_missing" in report["blockers"]
    assert "release_truth_authorization_missing" in report["blockers"]
