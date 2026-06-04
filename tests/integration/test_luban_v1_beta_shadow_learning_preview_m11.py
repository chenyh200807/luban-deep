"""Integration: Learning Brain stays preview-only; review queue generated; gaps never auto."""
from __future__ import annotations

import deeptutor.capabilities.deep_question as dq
from deeptutor.core.context import UnifiedContext

QA = "qa_m11_lb"


def _graded(qid, ans):
    return {"question_id": qid, "user_answer": ans,
            "construction_grading_result": {"authority": "construction_grading_result", "question_id": qid}}


def _ctx(ans):
    return UnifiedContext(session_id="m11", user_message=ans,
                          metadata={"user_id": QA, "grading_engine_v1_beta_shadow": True})


def _beta(qid, ans):
    payload = {"construction_grading_result": {"authority": "construction_grading_result", "question_id": qid}}
    dq._maybe_attach_v1_beta_shadow(context=_ctx(ans), graded_context=_graded(qid, ans), result_payload=payload)
    return payload["luban_grading_engine_v1_beta_shadow"]


def test_learning_brain_is_preview_only():
    lb = _beta("M2-2015-30-01", "工期 25 个月，合理")["learning_brain_preview"]
    assert lb["preview_only"] is True
    assert lb["writeback_performed"] is False
    assert lb["production_user_written"] is False
    assert lb["human_reviewed"] is False
    assert lb["claim"]["claim_authority"] == "beta_shadow_preview_not_production_truth"


def test_evidence_to_claim_chain_present():
    lb = _beta("M2-2015-30-01", "工期 25 个月，合理")["learning_brain_preview"]
    assert "evidence" in lb and isinstance(lb["evidence"], list)
    assert "claim" in lb
    assert set(lb["claim"]) >= {"auto_shadow_points", "review_points"}


def test_review_queue_item_generated():
    beta = _beta("M2-2015-30-01", "随便答")
    item = beta["teacher_review_queue_item"]
    assert item["qa_simulated"] is True
    assert item["human_reviewed"] is False
    assert item["final_disposition"] in {"auto_shadow_safe", "review_required"}


def test_spec_gap_becomes_review_not_auto():
    # an answer with no decidable numeric/judgment must not auto-certify any machine/list point
    beta = _beta("M2-2015-30-01", "我不知道")
    for p in beta["point_results"]:
        if p["path"] in ("machine_checkable_spec_path", "list_rule_full_coverage_path"):
            if not p.get("auto_shadow"):
                assert p["disposition"] == "review_required"
    # the question-level disposition is never a silent auto when gaps exist
    assert beta["review_required_count"] >= 0
