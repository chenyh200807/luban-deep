"""Hermetic guards for the M19E-R remote deployment authorization package.

No live calls, no remote anything. Asserts the package applies CORRECTED M19B semantics,
sources readiness from M19C/M19D (not the old _20260604 GO), isolates M20.1 as future_delta,
proposes a qa_/operator_-only limited default, attests no remote write, and keeps broad
default / canonical truth write prohibited with complete rollback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_r_20260605"
SCRIPT = REPO / "scripts/build_luban_remote_deployment_authorization_package_m19e_r.py"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text("utf-8"))


def _t(name: str) -> str:
    return (OUT / name).read_text("utf-8")


@pytest.fixture(scope="session", autouse=True)
def _ensure():
    if not (OUT / "no_remote_write_attestation_m19e_r.json").exists():
        if not SCRIPT.exists():
            pytest.skip("M19E-R builder absent")
        subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO, check=True, capture_output=True)
    return OUT


def test_corrected_m19b_semantics_applied():
    a = _j("corrected_m19b_application_audit_m19e_r.json")
    assert a["corrected_patch_read"] is True
    assert a["limited_default_candidate"] == "GO"
    assert a["production_default_flip_now"] == "NO-GO"
    assert a["rollback_measurement_bug_explained"] is True
    assert a["switch_paths_sub_second"] is True
    assert a["council_bare_word_block_not_veto"] is True
    assert a["substantive_block_required_for_veto"] is True
    assert a["old_2604_go_used_as_release_authority"] is False


def test_old_m19b_2604_not_canonical_release_authority():
    led = _j("canonical_lineage_ledger_m19e_r.json")
    assert led["old_m19b_20260604_go_is_canonical_release_authority"] is False
    arts = led["artifacts"]
    assert arts["production_default_decision_synthesis_m19b_20260604"]["role"] == "superseded"
    assert arts["production_default_decision_synthesis_m19b_20260604"]["retained"] is True


def test_m19c_m19d_are_current_readiness_source():
    r = _j("m19c_m19d_readiness_rollup_m19e_r.json")
    assert r["m19c"]["state"] == "local_ON"
    assert r["m19c"]["limited_default_enabled"] is True
    assert r["m19d"]["soak_verdict"] == "GO"
    assert r["m19d"]["keep_limited_default_on"] == "YES"
    assert r["m19d"]["false_positive"] == 0
    assert r["m19d"]["production_write_count"] == 0
    assert "M19C" in r["readiness_source_for_remote"] and "M19D" in r["readiness_source_for_remote"]


def test_m20_delta_isolated_as_future_delta():
    d = _j("m20_delta_isolation_audit_m19e_r.json")
    assert d["m20_role"] == "future_delta" and d["m201_role"] == "future_delta"
    assert d["isolated_from_current_runtime"] is True
    assert d["absorbed_into_m19c_m19d_runtime"] is False
    assert d["may_enter_runtime"] is False


def test_proposed_env_only_qa_operator():
    env = _t("proposed_remote_env_diff_m19e_r.md")
    assert "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true" in env
    assert "LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_" in env
    # no real-student / broad default leakage
    assert "broad production default" in env.lower()
    for forbidden in ("student_", "real_", "*", "all_users"):
        assert f"COHORT=qa_,operator_,{forbidden}" not in env


def test_no_remote_write_attestation():
    att = _j("no_remote_write_attestation_m19e_r.json")
    assert att["no_remote_write"] is True
    assert att["no_ssh_write_executed"] is True
    assert att["no_deploy_executed"] is True
    assert att["no_restart_executed"] is True
    assert att["remote_env_modified"] is False
    assert att["broad_production_default_opened"] is False
    assert att["canonical_truth_written"] is False
    assert att["published_registry_emitted"] is False
    assert att["staged_or_committed"] is False
    assert att["remote_write_root_if_authorized"] == "/root/deeptutor"


def test_rollback_commands_complete():
    rb = _t("rollback_commands_m19e_r.md")
    assert "env kill switch" in rb.lower()
    assert "LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false" in rb
    assert "registry" in rb.lower()
    assert "rollback_aliyun_release.sh" in rb  # code rollback
    sc = _j("stop_conditions_m19e_r.json")
    assert sc["hard_invariants_must_hold"]["broad_production_default"] is False
    assert sc["hard_invariants_must_hold"]["remote_write_outside_root"] is False


def test_broad_default_and_canonical_write_prohibited():
    form = _t("deployment_authorization_form_m19e_r.md")
    assert "broad production default" in form.lower()
    assert "NO-GO" in form
    assert "WAITING FOR EXPLICIT USER AUTHORIZATION" in form
    iso = _j("m20_delta_isolation_audit_m19e_r.json")
    assert iso["absorbed_into_m19c_m19d_runtime"] is False


def test_adversarial_review_all_resolved():
    adv = _j("adversarial_release_review_m19e_r.json")
    assert adv["all_resolved"] is True
    assert adv["unresolved"] == []
    for name, a in adv["attacks"].items():
        assert a["verdict"] in ("pass", "blocked", "requires_user_authorization")
    # the two over-claim risks must be blocked
    assert adv["attacks"]["old_rollback_false_treated_as_real_failure"]["verdict"] == "blocked"
    assert adv["attacks"]["bare_word_council_block_treated_as_veto"]["verdict"] == "blocked"


def test_deploy_commands_use_existing_runbook_only():
    cmds = _t("proposed_remote_commands_m19e_r.md")
    assert "NOT EXECUTED" in cmds
    assert "redeploy_aliyun_fast.sh" in cmds or "deploy_aliyun.sh" in cmds
    assert "DO NOT hand-run" in cmds  # forbids ad-hoc docker compose
    assert "/root/deeptutor" in cmds
