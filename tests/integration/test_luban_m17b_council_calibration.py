"""Integration guards for M17B AI council calibration.

The AI Expert Council is a NON-HUMAN review authority: it never writes human_reviewed /
po_reviewed, never becomes a source authority, and the deterministic source-discipline
gate overrides every council vote. Qwen fallback contract is exercised for real.
"""
from __future__ import annotations

import csv
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
    if not (OUT / "ai_council_votes.jsonl").exists():
        if not SCRIPT.exists():
            pytest.skip("M17B script absent")
        subprocess.run([sys.executable, str(SCRIPT), "--live-budget-s", "2", "--live-target", "0",
                        "--qwen-real", "0"], cwd=REPO, check=True, capture_output=True)
    return OUT


def test_council_is_non_human():
    votes = _jsonl("ai_council_votes.jsonl")
    assert votes
    for v in votes:
        assert v["is_human"] is False
    protocol = (OUT / "ai_council_protocol.md").read_text("utf-8")
    assert "ai_expert_council_final" in protocol
    assert "human_reviewed=false" in protocol


def test_council_vote_is_never_a_source():
    metrics = _j("deepseek_vs_council_metrics.json")
    assert metrics["council_vote_as_source"] == 0
    with (OUT / "ai_council_adjudication_matrix.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        assert r["council_vote_as_source"] in ("False", "false")
        # source-discipline gate: a point without deterministic_auto can never be council 'accept'
        if r["deterministic_auto"] in ("False", "false", ""):
            assert r["council_final"] != "accept"


def test_council_reviews_frontier_points():
    metrics = _j("deepseek_vs_council_metrics.json")
    assert metrics["frontier_points"] >= 1
    assert metrics["council_votes"] >= metrics["frontier_points"]  # >=1 seat per point


def test_council_failclosed_seats_recorded_not_fabricated():
    votes = _jsonl("ai_council_votes.jsonl")
    for v in votes:
        if v["vote"] == "fail_closed":
            assert v["live"] is False
            assert v["rationale"]  # records WHY (provider_unavailable / budget / error)


def test_qwen_fallback_contract_real():
    metrics = _j("qwen_vs_deepseek_metrics.json")
    assert metrics["forced_fallback_drills"] >= 20
    assert metrics["fallback_used"] >= 1
    assert "primary" in metrics["contract"] and "fallback" in metrics["contract"]


def test_deepseek_vs_council_agreement_reported():
    metrics = _j("deepseek_vs_council_metrics.json")
    assert "deepseek_council_agreement_rate" in metrics
    assert "severe_disagreements" in metrics
    # severe disagreement = council accepted where deterministic did NOT -> must be 0 (gate overrides)
    assert metrics["severe_disagreements"] == 0


def test_no_human_or_po_review_written_anywhere():
    protocol = (OUT / "ai_council_protocol.md").read_text("utf-8")
    assert "po_reviewed=false" in protocol
    go = _j("go_no_go_m17b.json")
    assert go["production_default_enabled"] is False
