"""M25-B: objective runtime adapter — bundle hit, tamper fail-closed, not-in-bank fail-open."""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading import objective_runtime_adapter as A
from deeptutor.services.construction_grading import objective_answer_key_compiler as C


@pytest.fixture(autouse=True)
def _clear_cache():
    A._candidate_index.cache_clear()
    yield
    A._candidate_index.cache_clear()


def test_objective_hit_grades_against_answer_key():
    # synthetic-obj-0001 answer_key A (single). Correct selection -> is_correct.
    p = A.build_objective_candidate_payload(question_id="synthetic-obj-0001", selected_option="A")
    assert p["mode"] == "objective_candidate"
    assert p["status"] == "candidate_unverified"
    assert p["llm_may_decide_correctness"] is False
    assert p["result"]["is_correct"] is True
    # wrong selection
    p2 = A.build_objective_candidate_payload(question_id="synthetic-obj-0001", selected_option="B")
    assert p2["result"]["is_correct"] is False


def test_multi_select_hit():
    # synthetic-obj-0002 answer_key ABD (multiple). Order-independent.
    p = A.build_objective_candidate_payload(question_id="synthetic-obj-0002", selected_option="DBA")
    assert p["result"]["is_correct"] is True


def test_not_in_bank_fail_open_open_world():
    p = A.build_objective_candidate_payload(question_id="does-not-exist-999", selected_option="A")
    assert p["mode"] == "open_world_fail_open"
    assert p["label"] == "unverified_diagnostic"
    assert p["official_answer_claimed"] is False
    assert p["auto_score"] is False
    assert p["compiler_work_order"]["promote_to_release"] is False


def test_tampered_bundle_fail_closed(monkeypatch):
    # Force the loaded bundle to fail verification -> fail-closed, no grade.
    good = C.build_candidate_bundle_from_seed()
    good["records"][0]["answer_key"] = "ZZZ"  # tamper without re-signing
    monkeypatch.setattr(C, "build_candidate_bundle_from_seed", lambda *a, **k: good)
    A._candidate_index.cache_clear()
    p = A.build_objective_candidate_payload(question_id="synthetic-obj-0001", selected_option="A")
    assert p.get("fail_closed") is True
    assert p["status"] == "candidate_bundle_unavailable"
    assert "result" not in p  # no grade emitted from a tampered bundle


def test_payload_never_claims_release_or_official():
    p = A.build_objective_candidate_payload(question_id="synthetic-obj-0003", selected_option="错")
    assert p["status"] == "candidate_unverified"
    assert p["not_production_grade"] is True
    assert p["writeback_performed"] is False
