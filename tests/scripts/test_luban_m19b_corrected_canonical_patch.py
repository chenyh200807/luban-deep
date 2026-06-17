"""Guards for the M19B corrected canonical patch.

These tests do NOT re-run the drill or make any live call. They assert the CORRECTED RISK
SEMANTICS are固化 — not merely that the verdict is GO, but that (1) the rollback false was a
measurement bug with switch-paths sub-second, and (2) a council bare-word block is advisory
and never a veto (only a substantive reasoned block can veto). Production default stays OFF
and no flip was executed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / "artifacts/luban_grading_artifacts/m19b_corrected_canonical_patch_20260605"
CANON = REPO / "artifacts/luban_grading_artifacts/production_default_decision_synthesis_m19b_20260605"

pytestmark = pytest.mark.skipif(not (PATCH / "corrected_verdict_m19b.json").exists(),
                                reason="M19B corrected patch absent")


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def test_corrected_five_axis_verdict():
    v = _j(PATCH / "corrected_verdict_m19b.json")["corrected_five_axis_verdict"]
    assert v["m19b_limited_production_default_candidate"] == "GO"
    assert v["production_default_flip_now"] == "NO-GO"
    assert v["broad_production_default"] == "NO-GO"
    assert v["production_v1_overall"] == "NO-GO"
    assert v["production_default"] == "OFF"
    assert v["default_flip_executed"] is False


def test_corrected_assertion_flags():
    flags = _j(PATCH / "corrected_verdict_m19b.json")["assertion_flags"]
    assert flags["rollback_measurement_bug_explained"] is True
    assert flags["switch_paths_sub_second"] is True
    assert flags["council_bare_word_block_not_veto"] is True
    assert flags["substantive_block_required_for_veto"] is True
    assert flags["production_default_off"] is True
    assert flags["default_flip_executed"] is False


def test_rollback_correction_documents_measurement_bug_not_failure():
    r = _j(PATCH / "corrected_verdict_m19b.json")["risk_correction_1_rollback_measurement_bug"]
    assert r["rollback_measurement_bug_explained"] is True
    assert r["true_rollback_facts"]["three_paths_state_correct"] is True
    assert r["true_rollback_facts"]["switch_paths_sub_second"] is True
    assert "state_correct" in r["m19c_requirement"] and "recover_ms" in r["m19c_requirement"]
    md = (PATCH / "rollback_metric_correction_m19b.md").read_text("utf-8")
    assert "measurement bug" in md.lower() and "grading" in md.lower()


def test_council_veto_policy_substantive_only():
    c = _j(PATCH / "corrected_verdict_m19b.json")["risk_correction_2_council_bare_word_block"]
    assert c["council_block_was_advisory_bare_word_artifact"] is True
    assert c["parser_not_at_fault"].startswith("raw model output")
    pol = c["policy"]
    assert pol["council_bare_word_block_not_veto"] is True
    assert pol["substantive_block_required_for_veto"] is True
    md = (PATCH / "council_veto_policy_correction_m19b.md").read_text("utf-8")
    assert "advisory" in md.lower() and "never" in md.lower()


def test_canonical_package_consistent_with_corrected_verdict():
    go = _j(CANON / "release_go_no_go_m19b.json")
    assert go["m19b_limited_production_default_candidate"] == "GO"
    assert go["production_default_flip_now"] == "NO-GO"
    assert go["production_default"] == "OFF"
    assert go["default_flip_executed"] is False
    assert go["rollback_three_paths_state_correct"] is True
    assert go["rollback_switch_paths_sub_second"] is True
    assert go["ai_council_substantive_block"] is False


def test_m19c_not_executed_and_default_not_opened():
    cv = _j(PATCH / "corrected_verdict_m19b.json")
    assert cv["corrected_five_axis_verdict"]["default_flip_executed"] is False
    assert "does NOT execute M19C" in cv["m19c_gate"]
    addendum = (PATCH / "m19c_preflight_addendum_m19b.md").read_text("utf-8")
    assert "does NOT execute M19C" in addendum or "does NOT open" in addendum
    # canonical dry-run config must still be DRY_RUN_ONLY
    dry = _j(CANON / "default_config_dryrun_m19b.json")
    assert dry["DRY_RUN_ONLY"] is True
    assert dry["default_flip_executed"] is False


def test_no_artifacts_deleted_supersession_only():
    cv = _j(PATCH / "corrected_verdict_m19b.json")
    assert "not deleted" in cv["supersedes"]["note"].lower() or "no artifacts deleted" in cv["supersedes"]["note"].lower()
    # both prior dirs still exist
    assert (REPO / "artifacts/luban_grading_artifacts/production_default_decision_synthesis_m19b_20260604").exists()
    assert CANON.exists()
