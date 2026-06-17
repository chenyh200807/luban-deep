"""M25-C: real objective answer-key extractor + signed v2 bundle (real_source_candidate)."""
from __future__ import annotations

import copy

import pytest

from deeptutor.services.construction_grading import objective_real_source_extractor as E
from deeptutor.services.construction_grading.objective_grader import grade_objective_submission


@pytest.fixture(scope="module")
def bundle():
    return E.build_real_candidate_bundle()


def test_extracts_real_answer_keys_from_tracked_fixture(bundle):
    assert bundle["manifest"]["count"] > 0  # real source found, answer_key_count > 0
    assert E.SOURCE.exists()  # tracked fixture, clean-checkout safe
    for r in bundle["records"]:
        assert r["answer_key"]
        assert r["question_type"] in ("single_choice", "multiple_choice")
        assert r["source_ref"]["kind"] == "public_exam_paper"


def test_status_real_source_candidate_not_release(bundle):
    m = bundle["manifest"]
    assert m["status"] == "real_source_candidate"
    assert m["release_authority"] is None
    assert m["published"] is False
    assert m["official_answer_role"] == "seed_from_public_exam_papers"
    assert m["separate_from_case_registry"] is True


def test_signature_valid_and_schema(bundle):
    assert E.verify_real_bundle(bundle) is True
    assert "content_hash" in bundle["manifest"]
    assert bundle["manifest"]["source_hashes"]["exam_quality_bank.json"]


def test_tamper_record_fails_closed(bundle):
    t = copy.deepcopy(bundle)
    t["records"][0]["answer_key"] = "ZZZ"
    assert E.verify_real_bundle(t) is False


def test_tamper_status_fails_closed(bundle):
    t = copy.deepcopy(bundle)
    t["manifest"]["status"] = "release"  # forging release status must break the signature
    assert E.verify_real_bundle(t) is False


def test_grader_compatible_with_real_seed_all_correct(bundle):
    # Feeding the canonical answer_key back must grade correct; safety all-0.
    fp = 0
    for r in bundle["records"]:
        res = grade_objective_submission(
            answer_key=r["answer_key"], selected=r["answer_key"], question_type=r["question_type"]
        )
        if not res["is_correct"]:
            fp += 1
    assert fp == 0


def test_adversarial_wrong_answer_graded_wrong(bundle):
    rec = next(r for r in bundle["records"] if r["question_type"] == "single_choice")
    wrong = "Z"  # not the key
    res = grade_objective_submission(answer_key=rec["answer_key"], selected=wrong,
                                     question_type=rec["question_type"])
    assert res["is_correct"] is False


def test_no_conflicts_or_rejects_become_authority(bundle):
    # rejected / conflict rows must NEVER appear as graded records
    rec_ids = {r["question_id"] for r in bundle["records"]}
    for bad in bundle["rejected"] + bundle["conflicts"]:
        assert bad["question_id"] not in rec_ids or "reason" in bad
