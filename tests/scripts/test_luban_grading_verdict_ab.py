"""Focused tests for the Nexus-vs-RAG grading verdict orchestrator.

Covers the deterministic logic only: gold-consensus mapping, typed-artifact
shaping, the 9-axis scorecard math, the typed-arm win/loss summary, slice
selection, and the end-to-end shape-tier safety invariants. No network.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import run_luban_arbitration_gold_panel as panel
from scripts import run_luban_grading_verdict_ab as verdict

# ---------------------------------------------------------------- gold consensus


def test_gold_consensus_drops_unadjudicated():
    rows = [
        {"case_id": "Q2", "student_id": "S1", "point_id": "P1", "consensus_verdict": "hit"},
        {"case_id": "Q2", "student_id": "S1", "point_id": "P2", "consensus_verdict": panel.UNADJUDICATED},
        {"case_id": "Q2", "student_id": "S2", "point_id": "P1", "consensus_verdict": "miss"},
    ]
    gold = verdict._gold_consensus(rows)
    assert gold == {("Q2", "S1", "P1"): "hit", ("Q2", "S2", "P1"): "miss"}
    assert ("Q2", "S1", "P2") not in gold  # unadjudicated never becomes a fake label


# ---------------------------------------------------------------- typed artifact


def test_typed_artifact_one_point_per_golden_point():
    case = {
        "case_id": "Q2",
        "max_score": 7,
        "stem": "stem",
        "gold_scoring_points": [
            {"point_id": "P1", "max_score": 2, "label": "L1", "official_basis": "B1"},
            {"point_id": "P2", "max_score": 5, "label": "L2", "official_basis": "B2"},
        ],
    }
    artifact = verdict._typed_artifact_for_case(case)
    assert artifact["artifact_schema"] == "case_grading_artifact.v1"
    pts = artifact["subquestions"][0]["scoring_points"]
    assert [p["point_id"] for p in pts] == ["P1", "P2"]
    assert [p["weight"] for p in pts] == [2.0, 5.0]  # weight == golden max_score
    assert artifact["output_contract"]["must_emit_one_result_per_point_id"] is True


def test_typed_artifact_validated_by_phase1_contract():
    """The typed artifact must round-trip through the Phase-1 locked validator:
    a complete per-point output passes; a collapsed one is contract_invalid."""
    from scripts import run_luban_student_answer_grading_eval as grading_eval

    case = {
        "case_id": "Q2", "max_score": 4, "stem": "s",
        "gold_scoring_points": [
            {"point_id": "P1", "max_score": 2, "label": "L1"},
            {"point_id": "P2", "max_score": 2, "label": "L2"},
        ],
    }
    context = {"typed_case_grading_artifact": verdict._typed_artifact_for_case(case)}
    full = {
        "score_pct": 50.0,
        "point_results": [
            {"point_id": pid, "sub_no": "1", "max_points": 2, "required_points": [],
             "accepted_variants": [], "student_evidence_quote": "q", "status": status,
             "awarded_points": awarded, "deduction_reason": ded, "misconception_tag": "t",
             "next_review_action": "r", "learning_evidence_event": {}}
            for pid, status, awarded, ded in [("P1", "hit", 2, ""), ("P2", "miss", 0, "漏列")]
        ],
    }
    ok = grading_eval.validate_grading_output(context, grading_eval.normalize_grading_payload(full))
    assert ok["status"] == "passed"

    collapsed = {"score_pct": 50.0, "point_results": [full["point_results"][0]]}  # P2 dropped
    bad = grading_eval.validate_grading_output(context, grading_eval.normalize_grading_payload(collapsed))
    assert bad["status"] == "contract_invalid"


# ---------------------------------------------------------------- scorecard math


def _gold(*triples_and_verdicts):
    return {(c, s, p): v for c, s, p, v in triples_and_verdicts}


def test_scorecard_axes_perfect_arm():
    gold = _gold(("Q", "S1", "P1", "hit"), ("Q", "S1", "P2", "miss"))
    arm_rows = [{
        "case_id": "Q", "student_id": "S1", "validation_status": "passed",
        "point_results": [
            {"point_id": "P1", "status": "hit", "awarded_points": 2, "max_points": 2,
             "deduction_reason": "", "misconception_tag": "", "student_evidence_quote": "q"},
            {"point_id": "P2", "status": "miss", "awarded_points": 0, "max_points": 2,
             "deduction_reason": "漏", "misconception_tag": "漏列", "student_evidence_quote": ""},
        ],
    }]
    sc = verdict._arm_scorecard("typed", arm_rows, gold)
    assert sc["compared_point_count"] == 2
    assert sc["axis1_hit_concordance"]["exact_agreement"] == 1.0  # arm matches gold exactly
    assert sc["axis2_validator_pass_rate"] == 1.0
    assert sc["axis6_miss_rate"] == 0.0      # gold hit was hit by arm
    assert sc["axis7_overcredit_rate"] == 0.0  # gold miss not over-credited
    assert sc["axis8_ordinal_mae"] == 0.0
    assert sc["axis9_field_compliance_rate"] == 1.0


def test_scorecard_counts_miss_and_overcredit():
    gold = _gold(("Q", "S1", "P1", "hit"), ("Q", "S1", "P2", "miss"))
    arm_rows = [{
        "case_id": "Q", "student_id": "S1", "validation_status": "contract_invalid",
        "point_results": [
            # gold=hit but arm says miss -> miss_rate; gold=miss but arm says hit -> overcredit
            {"point_id": "P1", "status": "miss", "awarded_points": 0, "max_points": 2,
             "deduction_reason": "漏", "misconception_tag": "t", "student_evidence_quote": ""},
            {"point_id": "P2", "status": "hit", "awarded_points": 2, "max_points": 2,
             "deduction_reason": "", "misconception_tag": "", "student_evidence_quote": "q"},
        ],
    }]
    sc = verdict._arm_scorecard("slim", arm_rows, gold)
    assert sc["axis6_miss_rate"] == 1.0       # the single gold-hit was missed
    assert sc["axis7_overcredit_rate"] == 1.0  # the single gold-miss was over-credited
    assert sc["axis2_validator_pass_rate"] == 0.0


def test_scorecard_absent_point_counts_as_miss_and_noncompliant():
    gold = _gold(("Q", "S1", "P1", "hit"))
    arm_rows = [{"case_id": "Q", "student_id": "S1", "validation_status": "passed",
                 "point_results": []}]  # arm emitted nothing for P1
    sc = verdict._arm_scorecard("slim", arm_rows, gold)
    assert sc["axis6_miss_rate"] == 1.0          # absent on a gold-hit == a miss
    assert sc["axis9_field_compliance_rate"] == 0.0  # no result object == non-compliant


# ---------------------------------------------------------------- verdict summary


def test_verdict_summary_typed_wins_on_auditability():
    # all three arms enforced a real contract -> axis2 is comparable
    cards = [
        {"arm": verdict.ARM_TYPED, "axis2_validator_pass_rate": 1.0, "axis2_contract_enforced": True,
         "axis9_field_compliance_rate": 1.0, "axis6_miss_rate": 0.1, "axis8_ordinal_mae": 0.2},
        {"arm": verdict.ARM_RUNTIME_SLIM, "axis2_validator_pass_rate": 0.0, "axis2_contract_enforced": True,
         "axis9_field_compliance_rate": 0.7, "axis6_miss_rate": 0.1, "axis8_ordinal_mae": 0.2},
        {"arm": verdict.ARM_KBV5, "axis2_validator_pass_rate": 0.0, "axis2_contract_enforced": True,
         "axis9_field_compliance_rate": 0.6, "axis6_miss_rate": 0.1, "axis8_ordinal_mae": 0.2},
    ]
    summary = verdict._verdict_summary(cards, quality_claim_allowed=True)
    assert "axis2_validator_pass_rate" in summary["typed_arm_wins_on"]
    assert "axis9_field_compliance_rate" in summary["typed_arm_wins_on"]
    assert summary["axis2_excluded_reason"] is None
    assert summary["interpretation"] == "typed_contract_arm_wins_on_auditability"
    assert summary["directional_only"] is False


def test_verdict_summary_excludes_axis2_when_others_pass_trivially():
    """The real observed asymmetry: typed enforces the locked schema (pass<1.0),
    slim/kbv5 have no typed artifact so they pass the validator trivially (1.0).
    That vacuous 1.0 must NOT be scored as a typed-arm loss on axis2."""
    cards = [
        {"arm": verdict.ARM_TYPED, "axis2_validator_pass_rate": 0.917, "axis2_contract_enforced": True,
         "axis1_hit_concordance": {"qwk": 0.95}, "axis4_tag_distinct_per_emitted": 0.05,
         "axis8_ordinal_mae": 0.08},
        {"arm": verdict.ARM_RUNTIME_SLIM, "axis2_validator_pass_rate": 1.0, "axis2_contract_enforced": False,
         "axis1_hit_concordance": {"qwk": 0.95}, "axis4_tag_distinct_per_emitted": 0.70,
         "axis8_ordinal_mae": 0.08},
        {"arm": verdict.ARM_KBV5, "axis2_validator_pass_rate": 1.0, "axis2_contract_enforced": False,
         "axis1_hit_concordance": {"qwk": 0.90}, "axis4_tag_distinct_per_emitted": 0.75,
         "axis8_ordinal_mae": 0.15},
    ]
    summary = verdict._verdict_summary(cards, quality_claim_allowed=True)
    # axis2 excluded -> not a loss; typed wins on tag stability (lower=better)
    assert "axis2_validator_pass_rate" not in summary["typed_arm_loses_on"]
    assert summary["axis2_excluded_reason"] == "other_arms_pass_validator_trivially_no_typed_contract"
    assert "axis4_tag_distinct_per_emitted" in summary["typed_arm_wins_on"]
    assert summary["interpretation"] == "typed_contract_arm_wins_on_auditability"


def test_verdict_summary_marks_directional_when_kappa_low():
    cards = [
        {"arm": verdict.ARM_TYPED, "axis2_validator_pass_rate": 1.0, "axis2_contract_enforced": True},
        {"arm": verdict.ARM_RUNTIME_SLIM, "axis2_validator_pass_rate": 0.0, "axis2_contract_enforced": True},
        {"arm": verdict.ARM_KBV5, "axis2_validator_pass_rate": 0.0, "axis2_contract_enforced": True},
    ]
    summary = verdict._verdict_summary(cards, quality_claim_allowed=False)
    assert summary["directional_only"] is True
    assert summary["quality_claim_allowed"] is False


# ---------------------------------------------------------------- slice / e2e


def test_unknown_case_rejected(tmp_path: Path):
    rc = verdict.main(["--cases", "Q-NOPE", "--tier", "shape", "--output-dir", str(tmp_path)])
    assert rc == 2


def test_live_tier_requires_double_opt_in(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(verdict.LIVE_ENV_FLAG, raising=False)
    rc = verdict.main(["--cases", "Q2-1A436000-罚则", "--tier", "live", "--output-dir", str(tmp_path)])
    assert rc == 2


def test_shape_tier_end_to_end_safe(tmp_path: Path):
    rc = verdict.main([
        "--cases", "Q2-1A436000-罚则,Q3-1A433000",
        "--tier", "shape", "--max-students", "2",
        "--output-dir", str(tmp_path),
    ])
    assert rc == 0
    report = json.loads((tmp_path / "verdict_scorecard.json").read_text(encoding="utf-8"))
    assert report["classification"] == "candidate_only"
    assert report["review_status"] == "review_only"
    assert report["production_write_count"] == 0
    assert report["safety"] == {
        "production_db_write": False, "canonical_truth_write": False,
        "published_registry_write": False, "remote_write": False,
    }
    assert report["arms"] == list(verdict.VERDICT_ARMS)
    assert len(report["scorecards"]) == 3
    # gold + scorecard + arm rows artifacts all written
    assert (tmp_path / "gold_panel.json").exists()
    assert (tmp_path / "arm_rows.json").exists()
    # the typed arm passes the locked contract; the looser arms do not
    by_arm = {sc["arm"]: sc for sc in report["scorecards"]}
    assert by_arm[verdict.ARM_TYPED]["axis2_validator_pass_rate"] == 1.0
    assert by_arm[verdict.ARM_RUNTIME_SLIM]["axis2_validator_pass_rate"] == 0.0
