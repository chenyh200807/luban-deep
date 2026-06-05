"""M5 LLM Jury adjudication protocol + fail-closed invariants.

`adjudicate` is a pure function driven here with SYNTHETIC votes (clearly test-only) to
exercise quorum / weak-upgrade / split / gate rules. `build_m5` is exercised with the live
provider adapter (no keys -> provider_unavailable) and with injected vote functions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_case_rubric_jury_review_m5 import adjudicate, build_m5, M4_DIR

pytestmark = pytest.mark.skipif(
    not (M4_DIR / "jury_review_packets").exists(), reason="M4 jury packets absent")


def _packet(qid="Q-T", points=None, weak_ids=()):
    pts = points or [{"point_id": "P1", "policy_type": "list_rule", "max_score": 2,
                      "source_status": "weak" if "P1" in weak_ids else "ok"}]
    return {"question_id": qid, "scoring_point_candidates": pts}


def _vote(model, decisions, anchor_ok=None, missing="low"):
    return {"model": model, "reviewer_type": "llm_jury", "votes_fabricated": False,
            "point_reviews": [{"point_id": pid, "decision": dec, "missing_point_risk": missing,
                               "textbook_anchor_ok": anchor_ok} for pid, dec in decisions.items()],
            "question_level_decision": "publish_candidate", "question_level_rationale": "t"}


def _m4(pub=True, draft=True, blockers=()):
    return {"can_enter_registry_published": pub, "can_enter_registry_draft": draft, "blockers": list(blockers)}


def test_quorum_under_3_fails_closed():
    pkt = _packet()
    votes = [_vote("gpt55", {"P1": "accept"}), _vote("opus48", {"P1": "accept"})]  # only 2
    adj = adjudicate(pkt, votes, _m4())
    assert adj["quorum_met"] is False
    assert adj["question_level_decision"] == "needs_po_review"


def test_three_of_four_accept_publishes_when_m4_gate_passes():
    pkt = _packet()
    votes = [_vote("gpt55", {"P1": "accept"}), _vote("opus48", {"P1": "accept"}),
             _vote("deepseek_v4", {"P1": "accept"}), _vote("qwen37", {"P1": "reject"})]
    adj = adjudicate(pkt, votes, _m4(pub=True, draft=True))
    assert adj["quorum_met"] is True
    assert adj["question_level_decision"] == "publish_candidate"


def test_two_two_split_needs_po_review():
    pkt = _packet()
    votes = [_vote("gpt55", {"P1": "accept"}), _vote("opus48", {"P1": "accept"}),
             _vote("deepseek_v4", {"P1": "reject"}), _vote("qwen37", {"P1": "reject"})]
    adj = adjudicate(pkt, votes, _m4())
    assert adj["question_level_decision"] == "needs_po_review"


def test_llm_cannot_upgrade_weak_source_to_verified():
    pkt = _packet(weak_ids=("P1",))
    votes = [_vote(m, {"P1": "accept"}, anchor_ok=True) for m in ("gpt55", "opus48", "deepseek_v4")]
    adj = adjudicate(pkt, votes, _m4())
    assert any("weak_anchor_upgrade_attempt_ignored" in nt for nt in adj["notes"])
    pr = adj["point_decisions"][0]
    assert pr["weak_upgrade_blocked"] is True


def test_calculation_without_spec_cannot_publish_even_if_all_accept():
    pkt = _packet()
    votes = [_vote(m, {"P1": "accept"}) for m in ("gpt55", "opus48", "deepseek_v4", "qwen37")]
    # M4 already gates published=False (calc without spec) but draft=True
    adj = adjudicate(pkt, votes, _m4(pub=False, draft=True, blockers=["calculation_without_spec"]))
    assert adj["question_level_decision"] == "draft_candidate"


def test_coverage_below_50_cannot_publish():
    pkt = _packet()
    votes = [_vote(m, {"P1": "accept"}) for m in ("gpt55", "opus48", "deepseek_v4")]
    adj = adjudicate(pkt, votes, _m4(pub=False, draft=True,
                                     blockers=["insufficient_verified_source_coverage(1/8)"]))
    assert adj["question_level_decision"] != "publish_candidate"


def test_high_missing_risk_majority_needs_po_review():
    pkt = _packet()
    votes = [_vote(m, {"P1": "accept"}, missing="high") for m in ("gpt55", "opus48", "deepseek_v4")]
    adj = adjudicate(pkt, votes, _m4())
    assert adj["question_level_decision"] == "needs_po_review"


def test_live_run_records_provider_unavailable_not_silently_skipped(tmp_path):
    r = build_m5(tmp_path)  # default _provider_vote, no keys -> all unavailable
    assert all(c == r["manifest"]["input_packets"] for c in r["provider_unavailable"].values())
    assert r["sim"]["registry_emitted"] is False
    assert r["sim"]["publish_ready_after_jury"] == 0
    assert r["sim"]["quorum_blocked"] == r["manifest"]["input_packets"]
    pu = list((tmp_path / "model_votes").glob("*__provider_unavailable.json"))
    assert pu  # recorded as files, not skipped


def test_fabricated_votes_are_rejected(tmp_path):
    def _fab(model, packet):
        return {"model": model, "votes_fabricated": True, "point_reviews": [],
                "question_level_decision": "publish_candidate"}
    with pytest.raises(AssertionError):
        build_m5(tmp_path, vote_fn=_fab)


def test_no_formal_registry_and_patches_do_not_overwrite_m4(tmp_path):
    r = build_m5(tmp_path)
    assert not (tmp_path / "registry_v1.json").exists()
    assert not (tmp_path / "question_grading_registry.json").exists()
    assert (tmp_path / "registry_v1_candidate_simulation_m5.json").exists()
    # M4 packets remain untouched (different dir)
    assert (M4_DIR / "jury_review_packets").exists()
