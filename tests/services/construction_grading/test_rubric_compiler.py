"""Rubric compiler — deterministic spine: score-sum gate, policy validation, dual-model reconcile."""
from __future__ import annotations

from deeptutor.services.construction_grading import rubric_compiler as RC


def _rubric(points, total, qid="Q1"):
    return {"qid": qid, "total_score": total,
            "scoring_points": [{"point_id": f"SP{i}", "text": t, "score": s, "policy": p,
                                "required_terms": rt} for i, (t, s, p, rt) in enumerate(points)]}


def test_valid_rubric_passes_score_sum_gate():
    r = _rubric([("不妥1", 2, "boolean_judgment", ["见证人员"]),
                 ("不妥2", 2, "boolean_judgment", ["建设单位"]),
                 ("列举6项", 3, "list", ["取样", "送检"])], total=7)
    v = RC.validate_rubric(r)
    assert v["ok"] and len(v["normalized"]["scoring_points"]) == 3


def test_validate_rubric_accepts_negative_evidence_list():
    rubric = {
        "qid": "QX",
        "total_score": 2,
        "scoring_points": [
            {
                "point_id": "P1",
                "text": "写明总时差不影响总工期",
                "score": 2,
                "policy": "qualitative",
                "required_terms": ["总时差"],
                "negative_evidence": ["水泥代号", "混凝土强度等级"],
            }
        ],
    }
    out = RC.validate_rubric(rubric)
    assert out["ok"] is True
    assert out["normalized"]["scoring_points"][0]["negative_evidence"] == ["水泥代号", "混凝土强度等级"]


def test_score_sum_mismatch_rejected():
    r = _rubric([("a", 2, "list", []), ("b", 2, "list", [])], total=7)  # 4 != 7
    v = RC.validate_rubric(r)
    assert not v["ok"] and "score_sum_mismatch" in v["reason"]


def test_unknown_policy_rejected():
    r = _rubric([("a", 5, "vibes", [])], total=5)
    assert not RC.validate_rubric(r)["ok"]


def test_to_signable_points_uses_reference_answer_provenance():
    r = RC.validate_rubric(_rubric([("麻面", 0.5, "exact_required", ["麻面"])], total=0.5))["normalized"]
    pts = RC.to_signable_points(r)
    assert pts[0]["source_refs"][0]["kind"] == "exam_reference_answer"  # NOT textbook verbatim
    assert pts[0]["authority_kind"] == "exact_required" and pts[0]["max_score"] == 0.5


def test_reconcile_prefers_finer_grained():
    opus = _rubric([("判断2点", 4, "boolean_judgment", []), ("列举", 3, "list", [])], total=7)
    codex = _rubric([("不妥1", 2, "boolean_judgment", []), ("不妥2", 2, "boolean_judgment", []),
                     ("项1", 1, "list", []), ("项2", 1, "list", []), ("项3", 1, "list", [])], total=7)
    out = RC.reconcile_dual_model(opus, codex)
    assert out["agree_total"] is True
    assert len(out["chosen"]["scoring_points"]) == 5  # finer-grained Codex chosen
    assert out["basis"] == "finer_grained"


def test_reconcile_falls_back_when_one_invalid():
    good = _rubric([("a", 5, "list", [])], total=5)
    bad = _rubric([("a", 2, "list", [])], total=5)  # sum mismatch
    out = RC.reconcile_dual_model(bad, good)
    assert out["chosen"] is not None and out["basis"] == "only_codex_valid"


def test_sign_rubric_release_candidate():
    rubrics = [_rubric([("麻面", 1, "exact_required", ["麻面"]), ("露筋", 1, "exact_required", ["露筋"])],
                       total=2, qid="Q1"),
               _rubric([("a", 3, "list", ["x"])], total=3, qid="Q2"),
               _rubric([("bad", 2, "list", [])], total=5, qid="Q3")]  # sum mismatch -> rejected
    out = RC.sign_rubric_release_candidate(rubrics)
    m = out["manifest"]
    assert m["question_count"] == 2 and m["scoring_point_count"] == 3
    assert m["rejected_count"] == 1
    assert m["answer_key_authority"] == "exam_reference_answer"  # not textbook verbatim
    # bundle verifies
    from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
    assert _sha256_hex(out["records"]) == m["content_hash"]
