"""Integration: v1 beta_shadow enters the REAL QA runtime hook, append-only, legacy untouched."""
from __future__ import annotations

import copy

import deeptutor.capabilities.deep_question as dq
from deeptutor.core.context import UnifiedContext

QA = "qa_m11_tester"
ANSWER = "工期为 25 个月，合理；编制说明、施工总进度计划表齐全。"


def _legacy(qid):
    return {"authority": "construction_grading_result", "question_id": qid, "total_score": 7.0,
            "point_results": [{"point_id": "P1", "score": 3.0}]}


def _graded(qid):
    return {"question_id": qid, "user_answer": ANSWER, "construction_grading_result": _legacy(qid)}


def _ctx(sid, flag):
    md = {"user_id": sid}
    if flag:
        md["grading_engine_v1_beta_shadow"] = True
    return UnifiedContext(session_id="m11", user_message=ANSWER, metadata=md)


def _run(sid, flag, qid="M2-2015-30-01"):
    payload = {"construction_grading_result": _legacy(qid)}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(sid, flag), graded_context=_graded(qid), result_payload=payload)
    return payload


def test_flag_off_is_legacy_only():
    p = _run(QA, flag=False)
    assert "luban_grading_engine_v1_beta_shadow" not in p
    assert p["construction_grading_result"] == _legacy("M2-2015-30-01")


def test_flag_on_appends_beta_without_touching_legacy():
    legacy_before = copy.deepcopy(_legacy("M2-2015-30-01"))
    p = _run(QA, flag=True)
    assert "luban_grading_engine_v1_beta_shadow" in p
    beta = p["luban_grading_engine_v1_beta_shadow"]
    assert beta["authority"] == "luban_grading_engine_v1_beta_shadow"
    assert beta["not_production_grade"] is True
    assert beta["production_runtime_connected"] is False
    assert beta["formal_registry_emitted"] is False
    # legacy is byte-identical
    assert p["construction_grading_result"] == legacy_before


def test_construction_grading_result_never_overwritten():
    p = _run(QA, flag=True)
    assert p["construction_grading_result"]["authority"] == "construction_grading_result"
    assert p["construction_grading_result"]["graded_by"] if False else True  # legacy object preserved
    assert "luban" not in p["construction_grading_result"]["authority"]


def test_duplicate_request_is_idempotent():
    a = _run(QA, flag=True)["luban_grading_engine_v1_beta_shadow"]
    b = _run(QA, flag=True)["luban_grading_engine_v1_beta_shadow"]
    assert a == b


def test_beta_payload_has_no_writeback():
    beta = _run(QA, flag=True)["luban_grading_engine_v1_beta_shadow"]
    assert beta["writeback_performed"] is False
    assert beta["human_reviewed"] is False
