"""M25-B: objective candidate lane integration through the deep_question runtime wrapper.

Exercises ``_maybe_attach_objective_candidate`` — the SAME append-only surface the /api/v1/ws
deep_question grading path invokes. Hermetic (no live LLM, no network).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeptutor.capabilities import deep_question as dq
from deeptutor.services.construction_grading import objective_runtime_adapter as A
from deeptutor.services.construction_grading import objective_answer_key_compiler as C


def _ctx(*, flag: bool, user_id: str = "qa_m25b"):
    metadata = {"user_id": user_id}
    if flag:
        metadata["grading_engine_objective_candidate"] = True
    return SimpleNamespace(metadata=metadata, config_overrides={})


def _legacy_payload():
    # legacy authority result that must NEVER be mutated by the objective lane
    return {"construction_grading_result": {"authority": "construction_grading", "is_correct": True}}


@pytest.fixture(autouse=True)
def _clear_cache():
    A._candidate_index.cache_clear()
    yield
    A._candidate_index.cache_clear()


def test_flag_off_legacy_byte_identical():
    payload = _legacy_payload()
    before = dict(payload["construction_grading_result"])
    dq._maybe_attach_objective_candidate(
        context=_ctx(flag=False),
        graded_context={"question_id": "synthetic-obj-0001", "user_answer": "A"},
        result_payload=payload,
    )
    assert "luban_grading_engine_objective_candidate" not in payload  # nothing appended
    assert payload["construction_grading_result"] == before  # legacy unchanged


def test_non_cohort_real_student_legacy_only():
    payload = _legacy_payload()
    dq._maybe_attach_objective_candidate(
        context=_ctx(flag=True, user_id="student_real_001"),
        graded_context={"question_id": "synthetic-obj-0001", "user_answer": "A"},
        result_payload=payload,
    )
    assert "luban_grading_engine_objective_candidate" not in payload


def test_objective_hit_appends_candidate_without_touching_legacy():
    payload = _legacy_payload()
    legacy_before = dict(payload["construction_grading_result"])
    dq._maybe_attach_objective_candidate(
        context=_ctx(flag=True),
        graded_context={"question_id": "synthetic-obj-0001", "user_answer": "A"},
        result_payload=payload,
    )
    appended = payload["luban_grading_engine_objective_candidate"]
    assert appended["status"] == "candidate_unverified"
    assert appended["result"]["is_correct"] is True
    assert appended["llm_may_decide_correctness"] is False
    assert payload["construction_grading_result"] == legacy_before  # legacy untouched (append-only)


def test_unknown_question_fail_open_open_world():
    payload = _legacy_payload()
    dq._maybe_attach_objective_candidate(
        context=_ctx(flag=True),
        graded_context={"question_id": "not-in-bank-xyz", "user_answer": "A"},
        result_payload=payload,
    )
    appended = payload["luban_grading_engine_objective_candidate"]
    assert appended["mode"] == "open_world_fail_open"
    assert appended["official_answer_claimed"] is False


def test_tamper_fail_closed_legacy_intact(monkeypatch):
    bad = C.build_candidate_bundle_from_seed()
    bad["records"][0]["answer_key"] = "ZZZ"
    monkeypatch.setattr(C, "build_candidate_bundle_from_seed", lambda *a, **k: bad)
    A._candidate_index.cache_clear()
    payload = _legacy_payload()
    legacy_before = dict(payload["construction_grading_result"])
    dq._maybe_attach_objective_candidate(
        context=_ctx(flag=True),
        graded_context={"question_id": "synthetic-obj-0001", "user_answer": "A"},
        result_payload=payload,
    )
    appended = payload["luban_grading_engine_objective_candidate"]
    assert appended.get("fail_closed") is True
    assert payload["construction_grading_result"] == legacy_before


def test_20_submissions_hermetic_safety_all_zero():
    """20 hermetic submissions across the seed bank; safety invariants all 0."""
    qids = ["synthetic-obj-0001", "synthetic-obj-0002", "synthetic-obj-0003"]
    answers = {"synthetic-obj-0001": ["A", "B"], "synthetic-obj-0002": ["ABD", "AB", "DBA"],
               "synthetic-obj-0003": ["错", "对"]}
    false_positive = answer_key_override = llm_changed_key = production_write = 0
    n = 0
    for i in range(20):
        qid = qids[i % len(qids)]
        sel = answers[qid][i % len(answers[qid])]
        payload = _legacy_payload()
        dq._maybe_attach_objective_candidate(
            context=_ctx(flag=True),
            graded_context={"question_id": qid, "user_answer": sel},
            result_payload=payload,
        )
        appended = payload["luban_grading_engine_objective_candidate"]
        n += 1
        # objective lane never writes production / never claims release
        if appended.get("writeback_performed"):
            production_write += 1
        if appended.get("status") not in ("candidate_unverified", "needs_review", "candidate_bundle_unavailable"):
            answer_key_override += 1
        if appended.get("llm_may_decide_correctness"):
            llm_changed_key += 1
        # a correct answer marked wrong (or vice versa) would be a false positive risk; check determinism
        if appended.get("mode") == "objective_candidate":
            res = appended["result"]
            # recompute independently
            from deeptutor.services.construction_grading.objective_grader import grade_objective_submission
            recomputed = grade_objective_submission(
                answer_key="A" if qid == "synthetic-obj-0001" else ("ABD" if qid == "synthetic-obj-0002" else "F"),
                selected=sel,
                question_type="true_false" if qid == "synthetic-obj-0003" else "choice",
            )
            if recomputed["is_correct"] != res["is_correct"]:
                false_positive += 1
    assert n == 20
    assert false_positive == 0
    assert answer_key_override == 0
    assert llm_changed_key == 0
    assert production_write == 0
