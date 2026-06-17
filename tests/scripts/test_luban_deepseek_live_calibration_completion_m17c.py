"""Guards for M17C DeepSeek live calibration completion.

M17C only closes M17B's live-call gap. Tests NEVER trigger live calls (live is gated behind
the script's --run-live flag); they validate the produced calibration artifacts: safety
invariants stay 0, no duplicated paid calls, the validator was re-run on every new live call,
and the merge math is consistent. The GO/WEAK-GO gate must follow merged>=80 honestly.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/deepseek_live_calibration_completion_m17c_20260604"
SCRIPT = REPO / "scripts/run_luban_deepseek_live_calibration_completion_m17c.py"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text("utf-8"))


def _jsonl(name: str) -> list[dict]:
    p = OUT / name
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()] if p.exists() else []


@pytest.fixture(scope="session", autouse=True)
def _ensure_m17c():
    # refresh artifacts WITHOUT live calls (resume-safe read of the checkpoint/rows)
    if not (SCRIPT.exists()):
        pytest.skip("M17C script absent")
    subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO, check=True, capture_output=True)  # no --run-live
    return OUT


def test_no_live_call_in_test_mode_and_merge_math_consistent():
    m = _j("merged_live_calibration_metrics_m17c.json")
    assert m["merged_deepseek_live_calls"] == m["m17a_live_calls"] + m["m17b_live_calls"] + m["m17c_new_live_calls"]


def test_safety_invariants_all_zero():
    s = _j("safety_invariant_report_m17c.json")
    for k in ("false_positive", "bad_certified", "source_mismatch", "official_answer_as_textbook",
              "model_vote_as_source", "council_vote_as_source", "list_partial_auto",
              "production_write_count", "duplicated_paid_calls"):
        assert s[k] == 0
    assert s["legacy_equal_rate"] == 1.0
    assert s["production_default_enabled"] is False
    assert s["secrets_printed"] is False
    assert s["safety_all_zero"] is True


def test_no_duplicated_paid_calls_resume_contract():
    resume = _j("deepseek_live_resume_state_m17c.json")
    assert resume["duplicated_paid_calls"] == 0
    assert "packet_hash" in resume["resume_key"]
    cost = _j("provider_rate_limit_and_cost_report_m17c.json")
    assert cost["duplicated_paid_calls"] == 0
    assert "backoff" in cost


def test_validator_rerun_on_every_new_live_call():
    rows = _jsonl("deepseek_live_calls_m17c.jsonl")
    for r in rows:
        # every new live call carries a validator verdict; fp/source_mismatch must be 0
        assert r["false_positive"] == 0
        assert r["source_mismatch"] == 0
        assert r["evidence_rich_full_policy"] is True
    downgrades = _jsonl("validator_recheck_results_m17c.jsonl")
    for d in downgrades:
        assert d["downgrade_reason"]
        assert d["auto_shadow_safe"] is False


def test_evidence_rich_full_policy_remains_default():
    ledger = _j("workflow_ledger_m17c.json")
    assert ledger["tournament"]["reused_winner"] == "evidence_rich_full_policy"
    assert ledger["tournament"]["not_rerun"] is True


def test_verdict_follows_merged_80_gate_honestly():
    go = _j("m19_default_decision_readiness_delta_m17c.json")
    ledger = _j("workflow_ledger_m17c.json")
    m = _j("merged_live_calibration_metrics_m17c.json")
    verdict = ledger["final_gate"]["verdict"]
    if m["merged_ge_80"]:
        assert verdict == "GO"
        assert go["m17_scaleout_axis"] == "GO"
    else:
        assert verdict == "WEAK-GO"
    # production guard holds regardless of verdict
    assert go["production_default"] == "OFF"
    assert go["production_v1"] == "NO-GO"


def test_supersession_matrix_records_merge_not_redo():
    matrix = (OUT / "m17a_m17b_m17c_supersession_matrix.md").read_text("utf-8")
    assert "Merged DeepSeek live calls" in matrix
    assert "NOT re-done" in matrix
