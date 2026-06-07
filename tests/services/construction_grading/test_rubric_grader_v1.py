"""Rubric grader v1 — LLM-adjudicated scoring-point grading -> GradingEvent -> learning evidence.

Hermetic: judge_fn is a deterministic stub (no LLM). Proves deterministic sum, exact_required binary,
partial credit, high-risk flag, and learning-evidence projection.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import rubric_grader_v1 as G


def _rubric():
    return [
        {"point_id": "P1", "text": "数控钢筋调直切断机", "score": 1.0, "policy": "exact_required",
         "required_terms": ["数控钢筋调直切断机"]},
        {"point_id": "P2", "text": "列举6项检验", "score": 3.0, "policy": "list", "required_terms": []},
        {"point_id": "P3", "text": "判断不妥并改正", "score": 2.0, "policy": "boolean_judgment", "required_terms": []},
    ]


def _judge(verdicts):
    def fn(point, answer):
        return verdicts.get(point["point_id"], {"status": G.MISS})
    return fn


def test_deterministic_sum_and_exact_required_binary():
    # P1 near-synonym (普通钢筋调直机) -> exact_required MISS (binary, no partial)
    # P2 list 4/6 -> partial 0.66 * 3 = 2.0; P3 hit -> 2.0
    judge = _judge({
        "P1": {"status": G.PARTIAL, "partial_ratio": 0.8, "evidence_span": "普通钢筋调直机"},  # exact->treated binary->miss
        "P2": {"status": G.PARTIAL, "partial_ratio": 0.66},
        "P3": {"status": G.HIT, "evidence_span": "总监理工程师组织"},
    })
    ev = G.grade_with_rubric(qid="Q1", student_answer="...", rubric_points=_rubric(), judge_fn=judge)
    pts = {p["point_id"]: p for p in ev["scoring_points"]}
    assert pts["P1"]["hit"] == G.MISS and pts["P1"]["score"] == 0.0       # exact_required binary
    assert pts["P1"]["mistake_type"] == G.MISTAKE_NEAR_SYNONYM
    assert abs(pts["P2"]["score"] - 1.98) < 0.01                          # 3 * 0.66
    assert pts["P3"]["score"] == 2.0
    assert ev["awarded_score"] == round(0 + 1.98 + 2.0, 2)
    assert ev["max_score"] == 6.0
    assert ev["official_score_allowed"] is False


def test_high_risk_on_low_confidence():
    judge = _judge({"P1": {"status": G.HIT, "low_confidence": True}, "P2": {"status": G.MISS}, "P3": {"status": G.MISS}})
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=_rubric(), judge_fn=judge)
    assert ev["high_risk_review"] is True


def test_learning_evidence_projection_lists_missed_points():
    judge = _judge({"P1": {"status": G.MISS}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}})
    ev = G.grade_with_rubric(qid="Q1", student_answer="x", rubric_points=_rubric(), judge_fn=judge, student_id="u1")
    le = G.to_learning_evidence(ev, node_code="1A413040")
    assert le["event_type"] == "learning_evidence"
    weak_ids = {w["concept_label"] for w in le["weak_points"]}
    assert "数控钢筋调直切断机" in weak_ids and "判断不妥并改正" in weak_ids  # the 2 missed
    assert all(w["concept_id"] == "1A413040" for w in le["weak_points"])
    assert le["writeback_performed"] is False
