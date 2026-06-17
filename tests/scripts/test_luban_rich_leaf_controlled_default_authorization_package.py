from __future__ import annotations

import json
from pathlib import Path


def _runtime_default_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_default_gate.v1",
        "verdict": "READY_FOR_CONTROLLED_DEFAULT_REVIEW",
        "quality_claim_allowed": False,
        "runtime_default_decision": {
            "default_install_allowed": False,
            "canonical_pointer_write_allowed": False,
            "requires_signed_operator_decision": True,
            "requires_rollback_plan": True,
            "requires_shadow_observability": True,
        },
        "summary": {
            "blocker_count": 0,
            "token_pack_unit_count": 102,
            "supply_unit_count": 102,
            "streaming_sample_count": 16,
            "streaming_provider_call_count": 32,
            "streaming_ttft_delta_ms": -43.57,
            "streaming_context_char_delta": -298.62,
            "semantic_live_ab_verdict": "PASS_LIVE_RUNTIME_AB_SHADOW",
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_default_gate": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
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


def test_controlled_default_authorization_package_requires_signature_without_installing() -> None:
    from scripts.run_luban_rich_leaf_controlled_default_authorization_package import (
        run_controlled_default_authorization_package,
    )

    report = run_controlled_default_authorization_package(runtime_default_gate=_runtime_default_gate())

    assert report["schema"] == "luban_rich_leaf_controlled_default_authorization_package.v1"
    assert report["verdict"] == "READY_FOR_OPERATOR_SIGNATURE"
    assert report["authorization_decision"]["operator_signature_recorded"] is False
    assert report["authorization_decision"]["controlled_default_authorized"] is False
    assert report["authorization_decision"]["canonical_pointer_write_allowed"] is False
    assert report["authorization_decision"]["production_db_write_allowed"] is False
    assert report["rollback_plan"]["plan_status"] == "draft_review_required"
    assert report["summary"]["blocker_count"] == 0
    assert report["summary"]["write_executed"] is False
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["production_default"] is False
    assert report["safety"]["production_write_count"] == 0


def test_controlled_default_authorization_package_accepts_frozen_v1_line_gate() -> None:
    from scripts.run_luban_rich_leaf_controlled_default_authorization_package import (
        run_controlled_default_authorization_package,
    )

    gate = _runtime_default_gate()
    gate["input_line"] = "frozen_v1"
    gate["input_schemas"] = {"runtime_token_pack": "luban_rich_leaf_runtime_token_pack.v2.3"}
    gate["summary"]["token_pack_unit_count"] = 1534
    gate["summary"]["semantic_live_ab_verdict"] = "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB"
    report = run_controlled_default_authorization_package(runtime_default_gate=gate)

    assert report["verdict"] == "READY_FOR_OPERATOR_SIGNATURE"
    assert report["input_line"] == "frozen_v1"
    assert report["candidate_scope"]["runtime_token_pack_unit_count"] == 1534
    assert report["candidate_scope"]["semantic_live_ab_verdict"] == "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB"
    # safety invariants unchanged on the frozen line
    assert report["authorization_decision"]["operator_signature_recorded"] is False
    assert report["authorization_decision"]["default_install_allowed"] is False
    assert report["summary"]["write_executed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_controlled_default_authorization_package_defaults_to_v1_legacy_line() -> None:
    from scripts.run_luban_rich_leaf_controlled_default_authorization_package import (
        run_controlled_default_authorization_package,
    )

    report = run_controlled_default_authorization_package(runtime_default_gate=_runtime_default_gate())

    assert report["input_line"] == "v1_legacy"


def test_controlled_default_authorization_package_blocks_on_gate_not_ready() -> None:
    from scripts.run_luban_rich_leaf_controlled_default_authorization_package import (
        run_controlled_default_authorization_package,
    )

    gate = _runtime_default_gate()
    gate["verdict"] = "BLOCKED"
    report = run_controlled_default_authorization_package(runtime_default_gate=gate)

    assert report["verdict"] == "BLOCKED"
    assert "runtime_default_gate_not_ready:BLOCKED" in report["blockers"]


def test_controlled_default_authorization_package_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_controlled_default_authorization_package import main

    gate = tmp_path / "runtime_default_gate.json"
    output = tmp_path / "controlled_default_authorization_package.json"
    gate.write_text(json.dumps(_runtime_default_gate(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--runtime-default-gate", str(gate), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "READY_FOR_OPERATOR_SIGNATURE"
    assert payload["summary"]["write_executed"] is False
