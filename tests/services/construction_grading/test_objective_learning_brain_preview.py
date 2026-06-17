"""M25-EF: objective->LB preview classification, no-mastery, isolation; v2 loader fail-closed."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from deeptutor.services.construction_grading import objective_learning_brain_preview as P
from deeptutor.services.construction_grading import v2_objective_supply_loader as L


def _payload(*, is_correct=None, missed=None, extra=None, selected="A", mode="objective_candidate",
             fail_closed=False):
    if mode == "open_world_fail_open":
        return {"mode": mode, "official_answer_claimed": False, "auto_score": False}
    if fail_closed:
        return {"fail_closed": True, "status": "candidate_bundle_unavailable"}
    return {"mode": mode, "answer_key_hash": "abc123", "authority_kind": "objective_answer_key_candidate",
            "source_refs": [{"ref": "q"}],
            "result": {"is_correct": is_correct, "score": 1.0 if is_correct else 0.0, "max_score": 1.0,
                       "missed": missed or [], "extra": extra or [],
                       "selected_option_normalized": selected, "correct_option_set_hash": "abc123"}}


def _evt(payload, user="qa_u", subject="construction_exam_1", qid="q1", variant="v"):
    return P.build_objective_evidence_event(payload, user_id=user, subject_id=subject,
                                            question_id=qid, variant=variant)


def test_correct_to_observed_strength_no_mastery():
    e = _evt(_payload(is_correct=True))
    assert e["outcome"] == "correct" and e["claim_kind"] == "observed_strength"
    assert e["retest_kind"] == "ready_retest"
    assert e["promoted_to_mastery"] is False and e["status"] == "candidate_unverified"


@pytest.mark.parametrize("kw,exp", [
    (dict(is_correct=False, selected="B"), "wrong"),
    (dict(is_correct=False, selected=""), "blank_or_invalid"),
    (dict(is_correct=False, missed=["C"], selected="AB"), "multi_missing"),
    (dict(is_correct=False, extra=["D"], selected="ABCD"), "multi_extra"),
])
def test_wrong_family_to_concept_gap(kw, exp):
    e = _evt(_payload(**kw))
    assert e["outcome"] == exp
    assert e["claim_kind"] == "concept_gap" and e["retest_kind"] == "needs_retest"


def test_open_world_unknown_no_official_score():
    e = _evt(_payload(mode="open_world_fail_open"), qid="unknown-x")
    assert e["outcome"] == "open_world_unknown"
    assert e["claim_kind"] == "diagnostic_draft"
    assert e["official_score"] is False
    wo = P.build_open_world_work_order(_payload(mode="open_world_fail_open"),
                                       user_id="qa_u", subject_id="s", question_id="unknown-x")
    assert wo["official_answer_claimed"] is False and wo["auto_score"] is False and wo["promote_to_release"] is False


def test_every_claim_has_supporting_event_and_not_mastery():
    e = _evt(_payload(is_correct=True))
    c = P.build_claim_proposal(e)
    assert c["supporting_event_ids"] == [e["event_id"]]
    assert c["unsupported"] is False and c["promoted_to_mastery"] is False
    assert c["generic_fallback"] is False  # specific (has qid + answer_key_hash)


def test_pcp_isolated_by_user_and_subject_no_leak():
    events = [
        _evt(_payload(is_correct=True), user="qa_a", subject="construction_exam_1", qid="q1"),
        _evt(_payload(is_correct=False, selected="B"), user="qa_b", subject="construction_exam_1", qid="q2"),
        _evt(_payload(is_correct=True), user="qa_a", subject="construction_exam_2", qid="q3"),
    ]
    pcp = P.build_pcp_preview(events, user_id="qa_a", subject_id="construction_exam_1")
    assert pcp["observed_strength_candidates"] == ["q1"]  # only qa_a + construction_exam_1
    for eid in pcp["next_action"]["supporting_event_ids"]:
        assert eid.startswith("obj-evt:")
    assert pcp["teacher_only_fields_present"] is False
    assert pcp["promoted_to_mastery"] is False


def test_retest_simulated_not_real():
    r = P.build_retest_plan(_evt(_payload(is_correct=False, selected="B")))
    assert r["simulated"] is True and r["simulated_retest_as_real"] is False
    assert r["supporting_event_ids"]


# ---- v2 supply loader ----
def test_loader_verifies_tracked_supply():
    r = L.load_and_verify()
    assert r["verified"] is True and r["status"] == "real_source_candidate" and len(r["index"]) == 62


def test_loader_tamper_and_missing_fail_closed():
    d = Path(tempfile.mkdtemp())
    shutil.copy(L._V2_DIR / "objective_answer_key_seed_real.jsonl", d)
    shutil.copy(L._V2_DIR / "runtime_supply_v2_manifest.json", d)
    seed = d / "objective_answer_key_seed_real.jsonl"
    lines = seed.read_text().splitlines()
    o = json.loads(lines[0]); o["answer_key"] = "ZZZ"; lines[0] = json.dumps(o, ensure_ascii=False)
    seed.write_text("\n".join(lines) + "\n")
    assert L.load_and_verify(d)["verified"] is False  # tamper
    seed.unlink()
    assert L.load_and_verify(d)["verified"] is False  # missing


def test_loader_rejects_published_or_bad_status(tmp_path):
    shutil.copy(L._V2_DIR / "objective_answer_key_seed_real.jsonl", tmp_path)
    man = json.loads((L._V2_DIR / "runtime_supply_v2_manifest.json").read_text())
    man["published"] = True
    (tmp_path / "runtime_supply_v2_manifest.json").write_text(json.dumps(man, ensure_ascii=False))
    assert L.load_and_verify(tmp_path)["verified"] is False
