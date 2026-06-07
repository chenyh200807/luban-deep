"""Fused case grading (V1 score authority + RAG/LLM teaching).

Hermetic: complete_fn / rag_fn are stubs (no LLM, no RAG). Proves the score comes ONLY from the V1
event (teaching never changes it), teaching is generated for missed points, RAG is optional, and the
teaching layer fails closed without breaking the authoritative score.
"""
from __future__ import annotations

import asyncio

from deeptutor.services.construction_grading.case_grading_fusion import build_fused_case_feedback


def _event(awarded=2.0, maximum=3.0):
    return {
        "event_type": "case_grading_completed",
        "awarded_score": awarded, "max_score": maximum,
        "scoring_points": [
            {"knowledge_point": "图1-1麻面", "hit": "hit", "score": 1.0, "max_score": 1.0},
            {"knowledge_point": "应编制临时用电方案", "hit": "miss", "score": 0.0, "max_score": 1.0,
             "mistake_type": "omitted"},
            {"knowledge_point": "专用开关箱", "hit": "partial", "score": 0.0, "max_score": 1.0,
             "mistake_type": "list_incomplete"},
        ],
        "official_score_allowed": False,
    }


async def _ok_complete(**_kw):
    return "【教学】漏掉的采分点要这样答…（记忆口诀）"


async def _boom_complete(**_kw):
    raise RuntimeError("llm down")


async def _rag(_q):
    return "教材依据：JGJ46 临时用电安全技术规范…"


def test_fusion_score_from_v1_only_teaching_added():
    out = asyncio.run(build_fused_case_feedback(
        _event(), question_stem="某案例", student_answer="我的作答",
        complete_fn=_ok_complete, api_key="k", rag_fn=None))
    # score authority = V1 event, never changed by teaching
    assert out["awarded_score"] == 2.0 and out["max_score"] == 3.0
    assert out["official_score_allowed"] is False
    # score block (V1) + teaching block present
    assert "【得分】2.0 / 3.0 分" in out["render"]
    assert "老师讲解" in out["render"] and "记忆口诀" in out["render"]
    assert out["teaching"]
    assert out["evidence_used"] is False


def test_fusion_uses_rag_evidence_when_available():
    out = asyncio.run(build_fused_case_feedback(
        _event(), question_stem="某案例", student_answer="x",
        complete_fn=_ok_complete, api_key="k", rag_fn=_rag))
    assert out["evidence_used"] is True
    assert "含教材依据" in out["render"]


def test_fusion_teaching_failure_keeps_authoritative_score():
    # teaching LLM fails -> teaching empty, but the V1 score block still renders intact (fail-safe)
    out = asyncio.run(build_fused_case_feedback(
        _event(), question_stem="某案例", student_answer="x",
        complete_fn=_boom_complete, api_key="k", rag_fn=None))
    assert out["teaching"] == ""
    assert "【得分】2.0 / 3.0 分" in out["render"]   # authoritative score unaffected
    assert "老师讲解" not in out["render"]            # no teaching block when teaching failed
    assert out["official_score_allowed"] is False


def test_fusion_all_hit_no_teaching():
    ev = {"event_type": "case_grading_completed", "awarded_score": 3.0, "max_score": 3.0,
          "scoring_points": [{"knowledge_point": "a", "hit": "hit", "score": 3.0, "max_score": 3.0}],
          "official_score_allowed": False}
    out = asyncio.run(build_fused_case_feedback(
        ev, question_stem="q", student_answer="x", complete_fn=_boom_complete, api_key="k"))
    assert out["teaching"] == ""                      # nothing missed -> no teaching needed
    assert "【得分】3.0 / 3.0 分" in out["render"]
