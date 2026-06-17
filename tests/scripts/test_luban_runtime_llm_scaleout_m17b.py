"""Guards for M17B runtime LLM scaleout + AI council calibration.

The deterministic validator is the sole auto judge: it must keep every safety invariant at
0 even when the LLM accepts everything or launders evidence. The AI council is a non-human
review authority that never becomes a source. Production default stays OFF.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/runtime_llm_scaleout_council_m17b_20260604"
SCRIPT = REPO / "scripts/run_luban_runtime_llm_scaleout_council_m17b.py"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text("utf-8"))


def _jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (OUT / name).read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _ensure_m17b():
    if not (OUT / "go_no_go_m17b.json").exists():
        if not SCRIPT.exists():
            pytest.skip("M17B script absent")
        subprocess.run([sys.executable, str(SCRIPT), "--live-budget-s", "2", "--live-target", "0",
                        "--qwen-real", "0"], cwd=REPO, check=True, capture_output=True)
    return OUT


def test_all_safety_invariants_zero():
    s = _j("runtime_safety_report.json")
    assert s["false_positive"] == 0
    assert s["bad_certified"] == 0
    assert s["source_mismatch"] == 0
    assert s["official_answer_as_textbook"] == 0
    assert s["model_vote_as_source"] == 0
    assert s["council_vote_as_source"] == 0
    assert s["list_partial_auto"] == 0
    assert s["legacy_equal_rate"] == 1.0
    assert s["production_write_count"] == 0
    assert s["production_default_enabled"] is False


def test_kill_failclosed_noncohort_hold():
    s = _j("runtime_safety_report.json")
    assert s["kill_switch_works"] is True
    assert s["artifact_fail_closed"] is True
    assert s["non_cohort_blocked"] is True


def test_scale_submissions_and_decisions_meet_floor():
    s = _j("go_no_go_m17b.json")["scale"]
    assert s["ws_submissions"] >= 120
    assert s["point_decisions"] >= 300


def test_validator_downgrades_block_adversarial_llm():
    adv = _j("adversarial_attack_results.json")
    # adversarial accept-all + laundering providers must NOT yield any false positive
    assert adv["total_false_positive"] == 0
    assert adv["source_laundering_blocked"] >= 1
    rows = _jsonl("validator_downgrade_audit.jsonl")
    for r in rows:
        assert r["downgrade_reason"]  # every downgraded point records why
        assert r["auto_shadow_safe"] is False


def test_qwen_fallback_drill_exercised():
    s = _j("go_no_go_m17b.json")["scale"]
    assert s["qwen_fallback_drills"] >= 20
    rows = _jsonl("qwen_fallback_drill_results.jsonl")
    assert any(r["fallback_used"] for r in rows)
    for r in rows:
        assert r["forced"] is True  # primary forced to fail -> fallback contract exercised


def test_packet_tournament_picks_validator_checkable_winner():
    t = _j("prompt_packet_tournament.json")
    assert t["winner"] == "evidence_rich_full_policy"
    assert t["variants"]["compact_minimal_ids"]["validator_checkable"] is False


def test_production_default_off_and_no_published_registry():
    go = _j("go_no_go_m17b.json")
    assert go["production_default"] == "OFF"
    assert go["production_default_enabled"] is False
    assert go["formal_registry_emitted"] is False
    assert go["three_axis"]["production_v1"] == "NO-GO"
    assert go["m17b_verdict"] in ("GO", "WEAK-GO")
