"""Integration: kill switch, non-qa guard, and fail-closed on artifact failure."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import deeptutor.capabilities.deep_question as dq
from deeptutor.core.context import UnifiedContext
from deeptutor.services.construction_grading import beta_shadow_loader as loader

ANSWER = "工期 25 个月"


def _legacy(qid):
    return {"authority": "construction_grading_result", "question_id": qid, "total_score": 7.0}


def _graded(qid):
    return {"question_id": qid, "user_answer": ANSWER, "construction_grading_result": _legacy(qid)}


def _ctx(sid):
    return UnifiedContext(session_id="m11", user_message=ANSWER,
                          metadata={"user_id": sid, "grading_engine_v1_beta_shadow": True})


def _run(sid, qid="M2-2015-30-01"):
    payload = {"construction_grading_result": _legacy(qid)}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(sid), graded_context=_graded(qid), result_payload=payload)
    return payload


def test_kill_switch_blocks_scoring(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_ENABLED", "false")
    beta = _run("qa_m11").get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None
    assert beta["shadow_status"] == "killed_by_switch"
    assert "point_results" not in beta  # no scoring happened


def test_kill_switch_absent_allows_flag(monkeypatch):
    monkeypatch.delenv("LUBAN_V1_BETA_SHADOW_ENABLED", raising=False)
    beta = _run("qa_m11").get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None and beta["shadow_status"] == "ok"


def test_non_qa_student_never_gets_beta():
    assert "luban_grading_engine_v1_beta_shadow" not in _run("real_student_7")


def test_artifact_missing_fails_closed():
    with pytest.raises(loader.BetaSupplyUnavailable):
        loader.load_beta_supply(root=Path("/tmp/__luban_m11_nonexistent__"))


def test_artifact_malformed_fails_closed(tmp_path: Path):
    bad = tmp_path / "non_textbook_rubric_authority_factory_m10_bad"
    bad.mkdir()
    (bad / "residual_authority_inventory_m10.json").write_text("{not json", "utf-8")
    (bad / "machine_checkable_case_specs_m10.jsonl").write_text("{bad json\n", "utf-8")
    for f in ("list_rule_structured_specs_m10.jsonl", "review_required_packets_m10.jsonl",
              "external_source_work_orders_m10.jsonl"):
        (bad / f).write_text("", "utf-8")
    with pytest.raises(loader.BetaSupplyUnavailable):
        loader.load_beta_supply(root=tmp_path)


def test_wrapper_fail_closed_keeps_legacy(monkeypatch):
    # force the loader to raise inside the wrapper -> beta marked unavailable, legacy intact
    monkeypatch.setattr(
        "deeptutor.services.construction_grading.beta_shadow_loader.build_beta_shadow_payload",
        lambda **kw: (_ for _ in ()).throw(loader.BetaSupplyUnavailable("boom")),
    )
    p = _run("qa_m11")
    assert p["construction_grading_result"]["authority"] == "construction_grading_result"
    beta = p["luban_grading_engine_v1_beta_shadow"]
    assert beta["shadow_status"] == "beta_supply_unavailable"
    assert beta["writeback_performed"] is False
