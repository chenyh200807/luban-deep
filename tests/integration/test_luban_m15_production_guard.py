"""M15 production guard: all safety invariants hold; production default OFF; no formal registry."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "artifacts/luban_grading_artifacts/runtime_hits_expansion_and_retest_entry_m15_20260604"


def _j(n):
    return json.loads((OUT / n).read_text("utf-8"))


def test_safety_invariants_all_clean():
    g = _j("kill_failclosed_legacy_guard_m15.json")
    assert g["kill_switch_works"] is True
    assert g["artifact_fail_closed"] is True
    assert g["non_cohort_blocked"] is True
    assert g["legacy_equal_rate"] == 1.0
    assert g["legacy_overwritten"] is False
    assert g["flag_off_beta_leak"] is False
    assert g["production_write_count"] == 0
    assert g["duplicate_idempotent"] is True


def test_non_cohort_users_blocked():
    g = _j("kill_failclosed_legacy_guard_m15.json")
    for c in g["cohort_audit"]:
        assert c["got_beta"] is False


def test_verdicts_and_production_no_go():
    v = _j("m15_go_no_go.json")
    assert v["production_v1"] == "NO-GO"
    assert v["production_default"] == "OFF"
    assert v["formal_registry_emitted"] is False
    assert v["m15_limited_internal_release_candidate"] in {"GO", "WEAK-GO", "NO-GO"}
    assert v["learning_brain_canonical_write_pilot"] in {"GO", "WEAK-GO", "NO-GO"}
    # if release GO it must be safe + hits>=50
    if v["m15_limited_internal_release_candidate"] == "GO":
        m = v["metrics"]
        assert m["counted_authority_backed_runtime_hits"] >= 50
        assert m["false_positive"] == 0 and m["production_write_count"] == 0


def test_no_production_truth_written():
    v = _j("m15_go_no_go.json")
    assert v["metrics"]["production_truth_written"] is False
    assert "m16_production_gate_blockers" in v and len(v["m16_production_gate_blockers"]) >= 1
