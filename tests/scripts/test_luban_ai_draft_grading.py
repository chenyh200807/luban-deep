from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_ai_draft_grading import (
    DRAFT_MARKERS,
    _cached_preds,
    _sample_set,
    ai_draft_grade,
    apply_guards,
    build_run_summary,
)


def test_run_summary_completion_rate_is_by_selected_not_available() -> None:
    # 50 drafts of a 50-sample selection out of 100 available -> 100% selected completion (not 50%)
    drafts = [{"question_id": f"Q{i}", "student_id": "S1", "point_count": 2, "latency_s": 1.0,
               "parse_status": "ok", "unsupported_count": 0, "high_risk_review_count": 0, "auto_certified_count": 2}
              for i in range(50)]
    keys = {(f"Q{i}", "S1") for i in range(50)}
    s = build_run_summary(drafts, keys, available_samples=100)
    assert s["available_samples"] == 100
    assert s["selected_samples"] == 50
    assert s["completed_selected_samples"] == 50
    assert s["selected_completion_rate"] == 1.0  # NOT 0.5
    assert "target_samples" not in s and "completion_rate" not in s  # misleading keys removed

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_consensus_gold/ai_draft_test_20260604"


def _question():
    return {
        "case_id": "QX", "max_score": 6, "official_answer": "...", "penalty_rule": "",
        "scoring_points": [
            {"point_id": "P1", "max_score": 2, "typed_policy": {"policy_type": "exact_required", "required_terms": ["数控钢筋调直切断机"]}},
            {"point_id": "P2", "max_score": 2, "typed_policy": {"policy_type": "list_rule", "required_terms": ["甲", "乙"], "denominator": 2}},
            {"point_id": "P3", "max_score": 2, "typed_policy": {"policy_type": "exact_required", "required_terms": ["专项施工方案"]}},
        ],
    }


# ---- draft markers ----

def test_draft_is_marked_candidate_only_and_shadow() -> None:
    student = "我写了甲和乙；还有专项施工方案"
    preds = [
        {"point_id": "P1", "hit": "miss", "score": 0, "evidence_span": "", "rationale": "未写"},
        {"point_id": "P2", "hit": "hit", "score": 2, "evidence_span": "甲和乙", "rationale": "命中甲乙"},
        {"point_id": "P3", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "逐字命中"},
    ]
    d = ai_draft_grade(_question(), student, predictions=preds, build_preview=False)
    assert d["authority"] == "ai_draft_shadow"
    assert d["candidate_only"] is True and d["not_production_grade"] is True
    assert d["protocol_version"] == DRAFT_MARKERS["protocol_version"]


# ---- span guard fail-closed: positive without verbatim span -> unsupported ----

def test_unsupported_positive_fail_closed() -> None:
    student = "我答了一些内容"
    preds = [
        {"point_id": "P2", "hit": "hit", "score": 2, "evidence_span": "甲乙丙丁", "rationale": "x"},  # span not in answer
    ]
    g = apply_guards(preds, _question()["scoring_points"], student)
    p = g[0]
    assert p["unsupported"] is True
    assert p["auto_certified"] is False  # unsupported is never auto-certified


def test_verbatim_span_is_supported() -> None:
    student = "答案包含 甲 和 乙 两项"
    preds = [{"point_id": "P2", "hit": "hit", "score": 2, "evidence_span": "甲 和 乙", "rationale": "命中"}]
    g = apply_guards(preds, _question()["scoring_points"], student)
    assert g[0]["unsupported"] is False


# ---- high_risk_review is never auto_certified ----

def test_high_risk_point_not_auto_certified() -> None:
    student = "用了普通钢筋调直机的工艺"
    preds = [
        # exact_required, rationale admits near-synonym/half term -> fallback -> high_risk
        {"point_id": "P1", "hit": "partial", "score": 1, "evidence_span": "普通钢筋调直机", "rationale": "只写了一半，缺少数控钢筋调直切断机"},
    ]
    g = apply_guards(preds, _question()["scoring_points"], student)
    p = g[0]
    assert p["high_risk_review"] is True
    assert p["auto_certified"] is False


def test_clean_exact_required_hit_is_auto_certified() -> None:
    student = "采用了专项施工方案进行施工"
    preds = [{"point_id": "P3", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "逐字命中官方术语"}]
    g = apply_guards(preds, _question()["scoring_points"], student)
    assert g[0]["auto_certified"] is True
    assert g[0]["high_risk_review"] is False
    assert g[0]["unsupported"] is False


# ---- dry_run reuses existing learning_evidence payload, no write ----

def test_payload_preview_reuses_existing_builder() -> None:
    student = "采用了专项施工方案"
    preds = [{"point_id": "P3", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "命中"}]
    d = ai_draft_grade(_question(), student, predictions=preds, build_preview=True)
    # the preview must be produced by the EXISTING learning_evidence builder (no new table/schema)
    assert "learning_evidence_payload_preview" in d
    assert "learning_evidence_payload_preview_error" not in d
    prev = d["learning_evidence_payload_preview"]
    assert isinstance(prev, dict) and prev  # non-empty payload dict


def test_total_score_excludes_high_risk_and_unsupported() -> None:
    student = "采用了专项施工方案"
    preds = [
        {"point_id": "P3", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "命中"},
        {"point_id": "P1", "hit": "partial", "score": 1, "evidence_span": "普通钢筋调直机", "rationale": "近义,缺少数控钢筋调直切断机"},  # high_risk
    ]
    # P1 not in student answer span -> unsupported too; either way excluded
    d = ai_draft_grade(_question(), student, predictions=preds, build_preview=False)
    # only the clean P3 (score 2) counts toward certified total
    assert d["total_score_certified_only"] == 2.0


# ---- Task B/D: score semantics + full-run schema ----

def test_full_run_draft_schema_and_score_semantics() -> None:
    student = "采用了专项施工方案；还有甲和乙"
    preds = [
        {"point_id": "P3", "hit": "hit", "score": 2, "evidence_span": "专项施工方案", "rationale": "命中"},
        {"point_id": "P2", "hit": "hit", "score": 2, "evidence_span": "甲和乙", "rationale": "命中甲乙"},
        {"point_id": "P1", "hit": "partial", "score": 1, "evidence_span": "普通钢筋调直机", "rationale": "近义,缺少数控钢筋调直切断机"},
    ]
    d = ai_draft_grade(_question(), student, predictions=preds, student_id="S1", build_preview=False)
    for key in ("parse_status", "expected_point_count", "model_draft_score", "auto_certified_score",
                "pending_review_score", "student_id", "score_semantics_note"):
        assert key in d
    assert d["parse_status"] == "ok"
    assert d["student_id"] == "S1"
    # model_draft_score >= auto_certified_score (pending points carry score but are not certified)
    assert d["model_draft_score"] >= d["auto_certified_score"]
    # pending_review_score is NOT folded into auto_certified_score; total alias == auto_certified
    assert d["total_score_certified_only"] == d["auto_certified_score"]
    assert d["pending_review_score"] > 0  # the near-synonym P1 carries a non-zero 待复核 score, not 0


def test_pending_review_score_is_not_in_certified() -> None:
    student = "用了普通钢筋调直机"
    preds = [{"point_id": "P1", "hit": "partial", "score": 1.0, "evidence_span": "普通钢筋调直机", "rationale": "近义,缺少数控钢筋调直切断机"}]
    d = ai_draft_grade(_question(), student, predictions=preds, build_preview=False)
    assert d["auto_certified_score"] == 0.0          # the only point is high_risk -> not certified
    assert d["pending_review_score"] == 1.0          # but its score is preserved as 待复核, not 0
    assert d["model_draft_score"] == 1.0


def test_parse_status_mismatch_when_point_count_off() -> None:
    # only 1 prediction for a 3-point question -> mismatch
    d = ai_draft_grade(_question(), "x", predictions=[{"point_id": "P1", "hit": "miss", "score": 0, "evidence_span": ""}], build_preview=False)
    assert d["parse_status"] == "mismatch"


# ---- resume/cache: no duplicate real calls ----

def test_cached_preds_roundtrip(tmp_path) -> None:
    (tmp_path / "QX__S1.json").write_text(
        '{"case_id":"QX","student_id":"S1","predictions":[{"point_id":"P1","hit":"miss","score":0}]}', encoding="utf-8")
    preds = _cached_preds(tmp_path, "QX", "S1")
    assert preds and preds[0]["point_id"] == "P1"
    assert _cached_preds(tmp_path, "QX", "S2") is None  # absent -> None (would trigger a fresh call)


def test_sample_set_all_samples_and_filters() -> None:
    cases = [
        {"case_id": "Q1", "eval_samples": [{"student_id": "S1"}, {"student_id": "S2"}]},
        {"case_id": "Q2", "eval_samples": [{"student_id": "S1"}, {"student_id": "S2"}]},
    ]
    assert len(_sample_set(cases, all_samples=True, case_id="", limit=0, offset=0)) == 4
    assert len(_sample_set(cases, all_samples=False, case_id="", limit=0, offset=0)) == 2  # first eval each
    assert len(_sample_set(cases, all_samples=True, case_id="Q1", limit=0, offset=0)) == 2
    assert len(_sample_set(cases, all_samples=True, case_id="", limit=1, offset=2)) == 1


# ---- generated-artifact gate (smoke output, if produced) ----

@pytest.mark.skipif(not (OUT / "ai_draft_smoke_results.json").exists(), reason="smoke not run")
def test_smoke_output_is_dry_run_and_marked() -> None:
    s = json.loads((OUT / "ai_draft_smoke_results.json").read_text(encoding="utf-8"))
    assert s["dry_run"] is True
    for d in s["drafts"]:
        assert d["candidate_only"] is True
        # no point may be both high_risk and auto_certified
        for p in d["point_results"]:
            if p["high_risk_review"] or p["unsupported"]:
                assert p["auto_certified"] is False
