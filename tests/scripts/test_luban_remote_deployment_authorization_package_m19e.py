"""Hermetic checks for the M19E remote deployment authorization package.

The package is documentation/artifact-only. These tests must not run ssh,
deploy, restart, or live provider calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605"
SCRIPT = REPO / "scripts/run_luban_remote_deployment_authorization_package_m19e.py"

REQUIRED_FILES = {
    "remote_deployment_manifest_m19e.json",
    "current_local_state_audit_m19e.json",
    "m19c_m19d_evidence_ledger_m19e.json",
    "proposed_remote_env_diff_m19e.md",
    "proposed_remote_commands_m19e.md",
    "rollback_commands_m19e.md",
    "stop_conditions_m19e.json",
    "observability_checklist_m19e.md",
    "safety_adversarial_review_m19e.json",
    "deployment_authorization_form_m19e.md",
    "no_remote_write_attestation_m19e.json",
    "FINDING_remote_deployment_authorization_package_m19e_20260605.md",
}


def _run_builder() -> None:
    subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO, check=True, capture_output=True, text=True)


def _json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _text(name: str) -> str:
    return (OUT / name).read_text(encoding="utf-8")


def test_m19e_builder_emits_required_authorization_package_files():
    _run_builder()
    emitted = {path.name for path in OUT.iterdir() if path.is_file()}
    assert REQUIRED_FILES <= emitted


def test_no_remote_write_attestation_and_current_local_state():
    _run_builder()
    attestation = _json("no_remote_write_attestation_m19e.json")
    assert attestation["no_remote_write_attestation"] is True
    assert attestation["no_ssh_executed"] is True
    assert attestation["remote_env_modified"] is False
    assert attestation["deploy_or_restart_executed"] is False
    assert attestation["remote_write_root_if_authorized"] == "/root/deeptutor"

    state = _json("current_local_state_audit_m19e.json")
    assert state["m19c_limited_default_state"] == "ON"
    assert state["m19d_soak_verdict"] == "GO"
    assert state["remote_aliyun_written"] is False
    assert state["broad_production_default"] == "NO-GO"
    assert state["canonical_learner_truth_write"] == "NO-GO"


def test_proposed_env_only_enables_limited_qa_operator_default():
    _run_builder()
    env = _text("proposed_remote_env_diff_m19e.md")
    assert "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true" in env
    assert "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_" in env
    assert "BROAD_PRODUCTION_DEFAULT" not in env
    assert "CANONICAL_LEARNER_TRUTH_WRITE=true" not in env
    assert "qa_,test_,operator_" not in env
    assert "/root/deeptutor" in env


def test_rollback_commands_cover_three_paths():
    _run_builder()
    rollback = _text("rollback_commands_m19e.md")
    assert "env kill" in rollback.lower()
    assert "LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false" in rollback
    assert "flag off" in rollback.lower()
    assert "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false" in rollback
    assert "registry unavailable" in rollback.lower()
    assert "/root/deeptutor" in rollback


def test_stop_conditions_cover_safety_invariants():
    _run_builder()
    stop = _json("stop_conditions_m19e.json")
    safety = stop["safety_stop_conditions"]
    for key in (
        "false_positive",
        "bad_certified",
        "source_mismatch",
        "legacy_overwrite",
        "production_write_count",
        "canonical_truth_written",
        "non_cohort_default_leak",
        "kill_switch_failure",
        "malformed_registry_fail_open",
        "provider_failure_fail_open",
    ):
        assert key in safety
    assert stop["hard_boundaries"]["broad_production_default"] == "NO-GO"
    assert stop["hard_boundaries"]["canonical_learner_truth_write"] == "NO-GO"


def test_m20_delta_not_absorbed_into_current_default():
    _run_builder()
    manifest = _json("remote_deployment_manifest_m19e.json")
    assert manifest["m20_1_delta_included_in_current_default"] is False
    assert manifest["m20_1_delta_status"] == "future_delta_not_current_runtime"


def test_adversarial_review_resolves_required_risks():
    _run_builder()
    review = _json("safety_adversarial_review_m19e.json")
    assert review["all_risks_resolved_or_authorization_gated"] is True
    risks = {item["risk"]: item for item in review["risks"]}
    for risk in (
        "non_cohort_leak",
        "env_misconfig_broad_default",
        "registry_missing_fail_open",
        "provider_failure_fail_open",
        "rollback_commands_incomplete",
        "observability_missing_metrics",
        "m20_1_delta_absorbed",
    ):
        assert risk in risks
        assert risks[risk]["disposition"] in {"pass", "blocked", "requires_user_authorization"}


def test_authorization_form_waits_for_user_before_m19f():
    _run_builder()
    form = _text("deployment_authorization_form_m19e.md")
    assert "M19F" in form
    assert "等待用户显式授权" in form
    assert "不得执行" in form
