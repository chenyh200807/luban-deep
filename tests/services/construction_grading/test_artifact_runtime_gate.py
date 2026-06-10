"""Tests for the QuestionGradingArtifact runtime gate.

Deterministic: builds the registry in-memory from the golden projection. No DB, no
provider key, no RAG authority, no kernel.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import artifact_runtime_gate as gate
from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft
from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
)


def _draft(points):
    return {"point_results": [dict(p) for p in points]}


_PUBLISHED = "Q1-NA"  # published, P1 auto_certifiable
_DRAFT = "QD-SYNTH-DRAFT"  # synthetic: 0 auto-certifiable points, no high_risk -> draft
_SUM_MISMATCH = "Q20-1A413000"  # declared total != point sum -> blocked by score-sum gate
_BLOCKED = "Q15-NA"  # 0 auto-certifiable + high_risk_review point -> blocked

def _synthetic_draft_artifact(qid: str = "QD-SYNTH-DRAFT") -> dict:
    """A structurally valid artifact with 0 auto-certifiable points and no
    high-risk policy point: the canonical *draft* shape. The golden bank no
    longer contains a draft sample because its former drafts (Q18/Q20) carry
    genuine declared-total/point-sum mismatches and are now correctly blocked."""
    return {
        "question_id": qid,
        "case_id": qid,
        "version_id": "qga_v0_synth",
        "status": "draft",
        "status_reason": "no_auto_certifiable_points",
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "x",
                "max_score": 2.0,
                "policy_type": "qualitative",
                "auto_certifiable": False,
                "source_status": "missing",
            }
        ],
        "quality_gates": {
            "has_scoring_points": True,
            "has_policy_type": True,
            "has_max_score": True,
            "score_sum_ok": True,
            "expected_total_present": True,
            "source_refs_verified_rate": 0.0,
            "source_validity": 0.0,
            "source_pollution_count": 0,
            "source_pollution_reasons": [],
            "negative_evidence_present": False,
            "auto_certifiable_point_count": 0,
            "unsupported_required_terms": [],
            "blocked_reasons": [],
        },
    }


def _resolve_draft_gate():
    return gate.resolve_runtime_artifact_gate(
        _DRAFT, registry=QuestionGradingRegistry([_synthetic_draft_artifact(_DRAFT)])
    )


def test_resolve_missing_question_fails_closed():
    g = gate.resolve_runtime_artifact_gate("NO-SUCH-QUESTION")
    assert g.artifact_found is False
    assert g.artifact_status == gate.ARTIFACT_MISSING
    assert g.auto_certification_allowed is False
    assert g.blocked_reason == gate.ARTIFACT_MISSING


def test_resolve_published_draft_blocked_status():
    assert gate.resolve_runtime_artifact_gate(_PUBLISHED).artifact_status == "published"
    assert _resolve_draft_gate().artifact_status == "draft"
    assert gate.resolve_runtime_artifact_gate(_SUM_MISMATCH).artifact_status == "blocked"
    assert gate.resolve_runtime_artifact_gate(_BLOCKED).artifact_status == "blocked"


def test_published_auto_certifiable_point_stays_auto():
    g = gate.resolve_runtime_artifact_gate(_PUBLISHED)
    auto_pid = next(pid for pid, ok in g.point_auto_certification.items() if ok)
    draft = _draft([{"point_id": auto_pid, "score": 2, "auto_certified": True,
                     "high_risk_review": False, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is True
    assert p["display_status"] == "auto_certified"
    assert out["auto_certified_score"] == 2.0


def test_published_weak_point_is_downgraded_not_auto():
    g = gate.resolve_runtime_artifact_gate(_PUBLISHED)
    # a point not in the artifact's auto-certifiable set
    draft = _draft([{"point_id": "PX-NOT-CERTIFIABLE", "score": 2, "auto_certified": True,
                     "high_risk_review": False, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert p["high_risk_review"] is True
    assert gate.POINT_NOT_AUTO_CERTIFIABLE in p["review_reason"]
    assert out["auto_certified_score"] == 0.0
    assert out["pending_review_score"] == 2.0  # preserved, not zeroed


def test_draft_artifact_blocks_all_points():
    g = _resolve_draft_gate()
    draft = _draft([{"point_id": "P1", "score": 2, "auto_certified": True,
                     "high_risk_review": False, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert gate.ARTIFACT_NOT_PUBLISHED in p["review_reason"]
    assert out["auto_certified_score"] == 0.0
    assert out["pending_review_score"] == 2.0


def test_blocked_artifact_blocks_all_points():
    g = gate.resolve_runtime_artifact_gate(_BLOCKED)
    draft = _draft([{"point_id": "P1", "score": 1, "auto_certified": True,
                     "high_risk_review": False, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert gate.ARTIFACT_BLOCKED in p["review_reason"]
    assert out["artifact_gate"]["artifact_status"] == "blocked"


def test_missing_artifact_blocks_all_points():
    g = gate.resolve_runtime_artifact_gate("NO-SUCH-QUESTION")
    draft = _draft([{"point_id": "P1", "score": 2, "auto_certified": True,
                     "high_risk_review": False, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert gate.ARTIFACT_MISSING in p["review_reason"]
    assert out["artifact_gate"]["artifact_found"] is False


def test_gate_never_upgrades_unsupported_into_auto():
    # an unsupported point in a PUBLISHED auto-certifiable slot must stay unsupported.
    g = gate.resolve_runtime_artifact_gate(_PUBLISHED)
    auto_pid = next(pid for pid, ok in g.point_auto_certification.items() if ok)
    draft = _draft([{"point_id": auto_pid, "score": 0, "auto_certified": False,
                     "high_risk_review": False, "unsupported": True}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert p["unsupported"] is True
    assert p["display_status"] == "unsupported"


def test_gate_never_upgrades_existing_high_risk_into_auto():
    g = gate.resolve_runtime_artifact_gate(_PUBLISHED)
    auto_pid = next(pid for pid, ok in g.point_auto_certification.items() if ok)
    draft = _draft([{"point_id": auto_pid, "score": 1, "auto_certified": False,
                     "high_risk_review": True, "unsupported": False}])
    out = gate.apply_runtime_artifact_gate(draft, g)
    p = out["point_results"][0]
    assert p["auto_certified"] is False
    assert p["high_risk_review"] is True
    assert out["pending_review_score"] == 1.0  # not zeroed


def test_build_ai_draft_with_gate_applies_same_rule():
    # build_ai_draft accepts a resolved gate and applies the same downgrade.
    question = {"case_id": _DRAFT, "max_score": 2,
                "scoring_points": [{"point_id": "P1", "max_score": 2, "label": "x",
                                    "typed_policy": {"policy_type": "exact_required", "required_terms": ["甲"]}}]}
    preds = [{"point_id": "P1", "hit": "hit", "score": 2, "evidence_span": "甲", "rationale": "命中"}]
    g = _resolve_draft_gate()
    draft = build_ai_draft(question, "甲", preds, points=question["scoring_points"], artifact_gate=g)
    assert draft["artifact_gate"]["artifact_status"] == "draft"
    assert draft["point_results"][0]["auto_certified"] is False
    assert draft["auto_certified_score"] == 0.0


def test_best_quality_uses_same_gate():
    # Best-Quality forwards artifact_gate to build_ai_draft -> same downgrade, one rule.
    from deeptutor.services.construction_grading.best_quality_ai_draft import best_quality_draft

    question = {"case_id": _DRAFT, "max_score": 2,
                "scoring_points": [{"point_id": "P1", "max_score": 2, "label": "x",
                                    "typed_policy": {"policy_type": "exact_required", "required_terms": ["甲"]}}]}
    model_outputs = {
        "gpt": {"P1": {"point_id": "P1", "hit": "hit", "score": 2, "evidence_span": "甲"}},
        "opus": {"P1": {"point_id": "P1", "hit": "hit", "score": 2, "evidence_span": "甲"}},
        "deepseek": {"P1": {"point_id": "P1", "hit": "hit", "score": 2, "evidence_span": "甲"}},
    }
    g = _resolve_draft_gate()
    draft = best_quality_draft(question, "甲", model_outputs,
                               points=question["scoring_points"], artifact_gate=g)
    assert draft["artifact_gate"]["artifact_status"] == "draft"
    assert draft["point_results"][0]["auto_certified"] is False
    assert draft["engine"] == "best_quality_4model"


def test_gate_to_dict_shape():
    g = gate.resolve_runtime_artifact_gate(_PUBLISHED)
    d = g.to_dict()
    for key in ("artifact_found", "artifact_status", "artifact_version_id",
                "auto_certification_allowed", "blocked_reason", "point_auto_certification"):
        assert key in d
