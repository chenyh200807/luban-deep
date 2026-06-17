"""Limited-release cohort switch: env-extensible allowlist, production default unchanged.

The cohort gate (designed in M13) must default to ``qa_``/``test_`` only (production behaviour
unchanged), be extendable via ``LUBAN_V1_BETA_SHADOW_COHORT``, always block real students, and
never override the kill switch / flag-off precedence.
"""
from __future__ import annotations

import deeptutor.capabilities.deep_question as dq
from deeptutor.core.context import UnifiedContext

ANSWER = "工期为 25 个月，合理。"


def _graded(qid="M2-2015-30-01"):
    return {"question_id": qid, "user_answer": ANSWER,
            "construction_grading_result": {"authority": "construction_grading_result", "question_id": qid}}


def _ctx(uid, flag=True):
    md = {"user_id": uid}
    if flag:
        md["grading_engine_v1_beta_shadow"] = True
    return UnifiedContext(session_id="cohort", user_message=ANSWER, metadata=md)


def _run(uid, flag=True):
    p = {"construction_grading_result": {"authority": "construction_grading_result"}}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(uid, flag), graded_context=_graded(), result_payload=p)
    return p


def test_default_cohort_is_qa_test_only(monkeypatch):
    monkeypatch.delenv("LUBAN_V1_BETA_SHADOW_COHORT", raising=False)
    assert dq._v1_beta_shadow_cohort_prefixes() == ("qa_", "test_")
    assert dq._v1_beta_shadow_cohort_member("qa_a") is True
    assert dq._v1_beta_shadow_cohort_member("test_a") is True
    assert dq._v1_beta_shadow_cohort_member("operator_a") is False
    assert dq._v1_beta_shadow_cohort_member("real_99") is False


def test_production_default_unchanged_real_student_blocked(monkeypatch):
    monkeypatch.delenv("LUBAN_V1_BETA_SHADOW_COHORT", raising=False)
    assert "luban_grading_engine_v1_beta_shadow" not in _run("real_student_1")
    assert "luban_grading_engine_v1_beta_shadow" not in _run("operator_1")


def test_qa_cohort_member_gets_beta(monkeypatch):
    monkeypatch.delenv("LUBAN_V1_BETA_SHADOW_COHORT", raising=False)
    assert "luban_grading_engine_v1_beta_shadow" in _run("qa_member")


def test_env_extends_cohort_but_never_real(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_COHORT", "operator_, internal_")
    assert "operator_" in dq._v1_beta_shadow_cohort_prefixes()
    assert "luban_grading_engine_v1_beta_shadow" in _run("operator_x")
    assert "luban_grading_engine_v1_beta_shadow" in _run("qa_x")  # builtin always kept
    assert "luban_grading_engine_v1_beta_shadow" not in _run("real_student_2")  # real never in cohort


def test_flag_off_beats_cohort(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_COHORT", "operator_")
    assert "luban_grading_engine_v1_beta_shadow" not in _run("operator_x", flag=False)


def test_kill_switch_beats_cohort(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_COHORT", "operator_")
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_ENABLED", "false")
    beta = _run("operator_x").get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None and beta["shadow_status"] == "killed_by_switch"
    assert "point_results" not in beta
