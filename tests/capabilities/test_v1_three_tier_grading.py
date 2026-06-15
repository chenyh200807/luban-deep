"""V1 three-tier grading path coverage.

Verifies that _grade_one_case_v1 works correctly across all three tiers:
  Tier 1: compiled_rubric — question_id maps to a bank rubric (mocked)
  Tier 2: on_the_fly_reference — no compiled rubric but correct_answer present
  Tier 3: derived_from_stem — neither compiled rubric nor reference; uses question_stem
  Fallback: no stem, no reference -> {"status": "no_reference"}
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deeptutor.capabilities.deep_question import _grade_one_case_v1
from deeptutor.services.construction_grading import rubric_grader_v1 as _G


def _stubbed_G(*, rubric_points: list | None = None, extract_points: list | None = None,
               derive_points: list | None = None):
    """Build a minimal mock of the rubric_grader_v1 module interface used by _grade_one_case_v1."""
    g = MagicMock()
    g.load_rubric = MagicMock(return_value=rubric_points or [])
    g.normalize_points_to_nominal = _G.normalize_points_to_nominal
    g.extract_rubric_from_reference_async = AsyncMock(return_value=extract_points or [])
    g.derive_rubric_from_stem_async = AsyncMock(return_value=derive_points or [])
    return g


def _make_event(points: list) -> dict:
    return {
        "event_type": "case_grading_completed",
        "scoring_points": [{"point_id": p["point_id"], "hit": "hit", "score": p["score"],
                             "max_score": p["score"], "mistake_type": None, "evidence_span": "",
                             "knowledge_point": p["text"], "policy_type": p["policy"],
                             "required_terms": p.get("required_terms", [])}
                           for p in points],
        "awarded_score": sum(p["score"] for p in points),
        "max_score": sum(p["score"] for p in points),
        "high_risk_review": False,
        "degraded": False,
    }


def _stub_complete(**kw):
    return ""


# ---------------------------------------------------------------------------
# Tier 1: compiled rubric (in-bank question)
# ---------------------------------------------------------------------------
def test_tier1_compiled_rubric_grades_without_reference() -> None:
    rubric = [{"point_id": "P1", "text": "应由监理委托", "score": 2.0,
               "policy": "qualitative", "required_terms": []}]
    G = _stubbed_G(rubric_points=rubric)
    G.grade_with_batch_judge_async = AsyncMock(return_value=_make_event(rubric))

    ctx = {
        "question_id": "q_001",
        "user_answer": "监理委托有资质的检测机构",
        "correct_answer": "",  # intentionally empty — compiled rubric takes over
        "question_stem": "指出检测机构管理的不妥之处。",
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    event = asyncio.run(_grade_one_case_v1(ctx, student_id="s1", complete=_stub_complete,
                                            key="k", _G=G))

    assert event is not None
    assert event.get("event_type") == "case_grading_completed"
    assert event["rubric_provenance"] == "compiled_rubric"
    G.extract_rubric_from_reference_async.assert_not_called()
    G.derive_rubric_from_stem_async.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 2: on-the-fly reference extraction (reference present, no compiled rubric)
# ---------------------------------------------------------------------------
def test_tier2_on_the_fly_reference_when_no_compiled_rubric() -> None:
    extracted = [{"point_id": "P1", "text": "由建设单位委托", "score": 2.0,
                  "policy": "qualitative", "required_terms": []}]
    G = _stubbed_G(rubric_points=[], extract_points=extracted)
    G.grade_with_batch_judge_async = AsyncMock(return_value=_make_event(extracted))

    ctx = {
        "question_id": "",  # not in bank
        "user_answer": "应由建设单位委托具有资质的检测机构",
        "correct_answer": "由建设单位委托具有资质的检测机构进行检测",
        "question_stem": "指出检测机构管理的不妥之处。",
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    event = asyncio.run(_grade_one_case_v1(ctx, student_id="s2", complete=_stub_complete,
                                            key="k", _G=G))

    assert event is not None
    assert event.get("event_type") == "case_grading_completed"
    assert event["rubric_provenance"] == "on_the_fly_reference"
    G.extract_rubric_from_reference_async.assert_called_once()
    G.derive_rubric_from_stem_async.assert_not_called()


def test_open_world_ignores_analysis_as_scoring_reference() -> None:
    """`analysis` may be RAG/explanation text, not the current question's answer key.

    In open-world pasted cases, using it as rubric authority can grade the learner
    against a similar-but-wrong case. Without an explicit answer key, V1 must derive
    from the current stem instead of extracting from analysis.
    """
    wrong_analysis_points = [{
        "point_id": "P1",
        "text": "采用固定价格应注意明确包死价的种类",
        "score": 1.0,
        "policy": "qualitative",
        "required_terms": [],
    }]
    derived = [{
        "point_id": "P1",
        "text": "工程量清单强制性内容",
        "score": 2.0,
        "policy": "qualitative",
        "required_terms": [],
    }]
    G = _stubbed_G(rubric_points=[], extract_points=wrong_analysis_points, derive_points=derived)
    G.grade_with_batch_judge_async = AsyncMock(return_value=_make_event(derived))

    ctx = {
        "question_id": "",
        "user_answer": "工程量计算规则、工程量清单编制方法。",
        "correct_answer": "",
        "reference_answer": "",
        "analysis": "采用固定价格应注意明确包死价的种类，签约合同价12345万元。",
        "question_stem": "【问题】1. 工程量清单的强制性内容还有哪些？",
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    event = asyncio.run(_grade_one_case_v1(ctx, student_id="s2", complete=_stub_complete,
                                            key="k", _G=G))

    assert event is not None
    assert event.get("event_type") == "case_grading_completed"
    assert event["rubric_provenance"] == "derived_from_stem"
    assert event["scoring_points"][0]["knowledge_point"] == "工程量清单强制性内容"
    G.extract_rubric_from_reference_async.assert_not_called()
    G.derive_rubric_from_stem_async.assert_called_once()


# ---------------------------------------------------------------------------
# Tier 3: stem-only derivation (no compiled rubric, no reference, but stem present)
# ---------------------------------------------------------------------------
def test_tier3_derived_from_stem_when_no_reference_and_no_compiled_rubric() -> None:
    derived = [{"point_id": "P1", "text": "指出不妥之处", "score": 2.0,
                "policy": "qualitative", "required_terms": []}]
    G = _stubbed_G(rubric_points=[], derive_points=derived)
    G.grade_with_batch_judge_async = AsyncMock(return_value=_make_event(derived))

    ctx = {
        "question_id": "",  # not in bank
        "user_answer": "检测机构应由建设单位委托",
        "correct_answer": "",  # no reference
        "question_stem": "施工现场检测管理存在哪些不妥之处？请指出并说明正确做法。",
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    event = asyncio.run(_grade_one_case_v1(ctx, student_id="s3", complete=_stub_complete,
                                            key="k", _G=G))

    assert event is not None
    assert event.get("event_type") == "case_grading_completed"
    assert event["rubric_provenance"] == "derived_from_stem"
    G.extract_rubric_from_reference_async.assert_not_called()
    G.derive_rubric_from_stem_async.assert_called_once()


# ---------------------------------------------------------------------------
# Fallback: no reference, no stem -> no_reference marker
# ---------------------------------------------------------------------------
def test_fallback_no_reference_no_stem_returns_marker() -> None:
    G = _stubbed_G(rubric_points=[])

    ctx = {
        "question_id": "",
        "user_answer": "不妥，应由建设单位委托",
        "correct_answer": "",
        "question_stem": "",  # empty stem
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    result = asyncio.run(_grade_one_case_v1(ctx, student_id="s4", complete=_stub_complete,
                                             key="k", _G=G))

    assert result is not None
    assert result.get("status") == "no_reference"
    G.extract_rubric_from_reference_async.assert_not_called()
    G.derive_rubric_from_stem_async.assert_not_called()


# ---------------------------------------------------------------------------
# Empty answer -> None (no grading)
# ---------------------------------------------------------------------------
def test_empty_answer_returns_none() -> None:
    G = _stubbed_G()

    ctx = {
        "question_id": "q_001",
        "user_answer": "",
        "correct_answer": "应由建设单位委托",
        "question_stem": "检测机构管理不妥之处？",
        "construction_grading_result": {"type": "case", "max_score": 2.0},
    }
    result = asyncio.run(_grade_one_case_v1(ctx, student_id="s5", complete=_stub_complete,
                                             key="k", _G=G))
    assert result is None
