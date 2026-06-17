"""Integration guards for the M9 explainable product vertical slice.

The slice must be a learner-readable loop: grading -> evidence -> blocked reason ->
diagnosis -> Learning Brain event -> LearnerClaim projection ->
PersonalizationContextPack -> next action. It is preview/QA-only: no production learner
truth, no production personalization, no new DB schema.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_v1_beta_shadow_source_assault_m9 as m9

pytestmark = pytest.mark.skipif(
    not (m9.M8_DIR / "verified_source_candidates.jsonl").exists(),
    reason="M8 source-backed supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_m9():
    subprocess.run([sys.executable, str(m9.REPO / "scripts/run_luban_v1_beta_shadow_source_assault_m9.py")],
                   cwd=m9.REPO, check=True, capture_output=True)
    return m9.OUT_DIR


def test_at_least_ten_learner_visible_study_cards():
    cards = (m9.OUT_DIR / "learner_visible_study_cards_preview.md").read_text("utf-8")
    assert cards.count("## 学习卡") >= 10


def test_each_example_is_a_full_explainable_chain():
    examples = _jsonl(m9.OUT_DIR / "beta_shadow_grading_result_examples.jsonl")
    assert len(examples) >= 10
    required = {"grading_result", "point_evidence", "diagnosis",
                "learning_brain_event", "personalization_context_pack", "next_action"}
    for ex in examples:
        assert required.issubset(ex.keys())
        # evidence must point to a textbook anchor (not official answer / model vote)
        assert ex["point_evidence"]["source_authority"] == "textbook_exact_match"
        assert ex["grading_result"]["is_formal_score"] is False
        assert ex["grading_result"]["production_default_auto"] is False


def test_learning_brain_events_are_qa_backend_only():
    events = _jsonl(m9.OUT_DIR / "beta_shadow_learning_brain_events_preview.jsonl")
    assert events
    for e in events:
        assert e["production_user_written"] is False
        assert e["channel"] == "qa_test_backend_only"
        assert e["learner_claim_projection"]["authority"] == "alpha_beta_shadow_advisory_not_authoritative"


def test_personalization_pack_is_preview_only():
    pcp = _j(m9.OUT_DIR / "personalization_context_pack_preview.json")
    assert pcp["is_preview"] is True
    assert pcp["production_personalization_written"] is False
    assert len(pcp["packs"]) >= 10
    for p in pcp["packs"]:
        assert p["production_personalization_written"] is False
        assert "retest_plan" in p  # must explain how a retest proves progress


def test_final_gate_is_not_smuggling_alpha_or_beta_upward():
    gate = _j(m9.OUT_DIR / "m10_gated_beta_gate_m9.json")
    assert gate["m10_gated_beta_qa_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    c = gate["constraints"]
    assert c["formal_registry_emitted"] is False
    assert c["production_runtime_connected"] is False
    assert c["v0_overwritten"] is False
    assert c["alpha_not_smuggled_to_beta"] is True
    assert c["beta_not_smuggled_to_production"] is True
