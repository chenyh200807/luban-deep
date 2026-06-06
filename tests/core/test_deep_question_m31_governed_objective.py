"""M31: governed objective lane through the deep_question runtime wrapper.

Exercises ``_maybe_attach_m31_governed_objective`` — the SAME append-only surface the /api/v1/ws
deep_question grading path invokes — over a hermetic signed governed bundle. Proves flag/cohort/kill
gating, append-only legacy safety, and that an in-bank governed hit becomes CONTROLLED release-truth.
Hermetic (no live LLM, no network, no live DB).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.capabilities import deep_question as dq
from deeptutor.services.construction_grading import full_knowledge_compiler as fkc
from deeptutor.services.construction_grading import objective_runtime_adapter as A

_ROWS = [
    {"question_id": "WRAP_SC_1", "question_type": "single_choice",
     "stem": "临时用电几级配电？", "options": {"A": "三级", "B": "两级", "C": "一级", "D": "四级"},
     "official_answer": "A"},
]
KEY = "luban_grading_engine_m31_governed_objective"


@pytest.fixture
def governed_bundle(tmp_path, monkeypatch):
    bundle = fkc.compile_full_objective_release_candidate(_ROWS)
    (tmp_path / "objective_answer_key_release_candidate_m31.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    (tmp_path / "canonical_pointer_m31.json").write_text(json.dumps(
        {"namespace": "objective_answer_key_full", "status": "release_candidate", "published": False,
         "expected_content_hash": bundle["manifest"]["content_hash"], "coverage": "hermetic_test"}), "utf-8")
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "canonical_pointer_m31.json")
    monkeypatch.delenv("LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED", raising=False)
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()
    yield
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()


def _ctx(*, flag: bool, user_id: str = "qa_m31"):
    md = {"user_id": user_id}
    if flag:
        md["grading_engine_m31_governed_objective"] = True
    return SimpleNamespace(metadata=md, config_overrides={})


def _legacy_payload():
    return {"construction_grading_result": {"authority": "construction_grading", "is_correct": True}}


def test_flag_off_legacy_byte_identical(governed_bundle):
    payload = _legacy_payload()
    before = dict(payload["construction_grading_result"])
    dq._maybe_attach_m31_governed_objective(
        context=_ctx(flag=False),
        graded_context={"question_id": "WRAP_SC_1", "user_answer": "A"},
        result_payload=payload,
    )
    assert KEY not in payload
    assert payload["construction_grading_result"] == before


def test_non_cohort_real_student_legacy_only(governed_bundle):
    payload = _legacy_payload()
    dq._maybe_attach_m31_governed_objective(
        context=_ctx(flag=True, user_id="u_real_001"),
        graded_context={"question_id": "WRAP_SC_1", "user_answer": "A"},
        result_payload=payload,
    )
    assert KEY not in payload


def test_cohort_governed_hit_is_release_truth_legacy_untouched(governed_bundle):
    payload = _legacy_payload()
    legacy_before = dict(payload["construction_grading_result"])
    dq._maybe_attach_m31_governed_objective(
        context=_ctx(flag=True, user_id="qa_alice"),
        graded_context={"question_id": "WRAP_SC_1", "user_answer": "A"},
        result_payload=payload,
    )
    appended = payload[KEY]
    assert appended["mode"] == "governed_objective_release_candidate"
    assert appended["release_truth"] is True
    assert appended["controlled_official"] is True
    assert appended["result"]["is_correct"] is True
    assert appended["llm_may_decide_correctness"] is False
    assert payload["construction_grading_result"] == legacy_before  # append-only


def test_kill_switch_tombstone(governed_bundle, monkeypatch):
    monkeypatch.setenv("LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED", "off")
    payload = _legacy_payload()
    dq._maybe_attach_m31_governed_objective(
        context=_ctx(flag=True, user_id="qa_alice"),
        graded_context={"question_id": "WRAP_SC_1", "user_answer": "A"},
        result_payload=payload,
    )
    appended = payload[KEY]
    assert appended["status"] == "killed_by_switch"
    assert appended["killed_by_switch"] is True
    assert "result" not in appended  # no governed scoring happened


def test_operator_cohort_member_allowed(governed_bundle):
    payload = _legacy_payload()
    dq._maybe_attach_m31_governed_objective(
        context=_ctx(flag=True, user_id="operator_bob"),
        graded_context={"question_id": "WRAP_SC_1", "user_answer": "C"},
        result_payload=payload,
    )
    appended = payload[KEY]
    assert appended["mode"] == "governed_objective_release_candidate"
    assert appended["result"]["is_correct"] is False  # selected C, key A
    assert appended["release_truth"] is True
