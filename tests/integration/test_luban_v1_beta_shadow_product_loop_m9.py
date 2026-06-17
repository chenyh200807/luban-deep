"""Integration-style guard for the M9 beta-shadow product vertical slice.

Proves the QA grading product loop produces grading -> point evidence -> blocked
reason -> diagnosis -> Learning-Brain event -> learner-visible study card, and that
the beta-shadow grading view is append-only (never a production write, never a grade).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import scripts.run_luban_v1_beta_shadow_grand_sprint_m9 as m9

pytestmark = pytest.mark.skipif(
    not m9.FULL100.exists(), reason="full100 graded samples absent",
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def loop_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("m9_product")
    m9.run_m9(out_dir=out, live_models=False)
    return out


def test_product_loop_produces_grading_evidence_diagnosis_and_next_action(loop_out):
    examples = _jsonl(loop_out / "beta_shadow_grading_result_examples.jsonl")
    assert len(examples) >= 10
    for ex in examples:
        assert ex["authority"] == "ai_draft_shadow"
        assert ex["not_production_grade"] is True
        assert ex["point_views"]  # has graded points
        for pv in ex["point_views"]:
            assert "diagnosis" in pv and pv["diagnosis"]
            # blocked points carry a reason; auto-certified points carry textbook evidence
            if pv["blocked_reason"] is None and pv["auto_certified_by_kernel_shadow"]:
                assert pv["textbook_evidence_span"] is not None
        assert ex["next_action"]


def test_learning_brain_events_and_context_pack_are_dry_run(loop_out):
    events = _jsonl(loop_out / "beta_shadow_learning_brain_events_preview.jsonl")
    pack = _j(loop_out / "personalization_context_pack_preview.json")
    assert len(events) >= 10
    assert all(e.get("event_type") == "learning_evidence" for e in events)
    assert pack["dry_run"] is True
    assert pack["writeback_performed"] is False
    assert pack["production_runtime_connected"] is False
    assert pack["learners"]  # at least one learner projected


def test_learner_visible_study_cards_are_explainable_and_retestable(loop_out):
    cards_md = (loop_out / "learner_visible_study_cards_preview.md").read_text("utf-8")
    assert cards_md.count("## Card ") >= 10
    assert "哪里错" in cards_md
    assert "为什么" in cards_md
    assert "下一步练什么" in cards_md
    assert "可复测" in cards_md


def test_beta_shadow_grading_view_never_overwrites_legacy_grade():
    legacy = {
        "event": "RESULT",
        "metadata": {"construction_grading_result": {
            "score_awarded": 3, "max_score": 5, "authority": "CaseGradingSkillKernel"}},
    }
    before = copy.deepcopy(legacy)
    out = m9.build_beta_shadow_grading_view(
        legacy,
        {"beta_shadow_total_auto_preview": 87, "registry_status": m9.BETA_STATUS},
        enabled=True,
    )
    assert legacy == before
    assert out["metadata"]["construction_grading_result"] == before["metadata"]["construction_grading_result"]
    shadow = out["metadata"][m9.SHADOW_KEY]
    assert shadow["authority"] == m9.SHADOW_KEY
    assert shadow["writeback_performed"] is False
    assert shadow["scores"]["legacy_score_overwritten"] is False
