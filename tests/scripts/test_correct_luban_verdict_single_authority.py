"""Focused tests pinning the single-authority discipline of the Phase-3 verdict
scorecard correction.

The corrector is a pure-offline re-aggregation of already-landed artifacts:
the official answer key (``reference_ledger_label``) is the ONLY authority for
whether a scoring point landed; the AI arbitration panel is a noise-reduction
mirror and a key-error candidate flagger, never an authority. These tests lock:

  * accuracy axes join to ``reference_ledger_label`` (the key), never to
    ``consensus_verdict`` (the panel);
  * a high panel self-agreement kappa that disagrees with the key CANNOT grant a
    quality claim -- ``quality_claim_allowed`` must be False;
  * panel/key disagreements surface as owner-review candidates, never as key
    overrides;
  * structural axes (authority-agnostic) are preserved verbatim.

No network. No LLM. Deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import correct_luban_verdict_single_authority as corrector

# --------------------------------------------------------------- fixtures


def _gold_panel() -> dict:
    """Two points: one where panel agrees with key, one where the unanimous panel
    DISAGREES with the key (the key says hit, the panel says miss)."""
    rows = [
        {
            "case_id": "Q",
            "student_id": "S1",
            "point_id": "P1",
            "blind_votes": {"a": "hit", "b": "hit", "c": "hit"},
            "route": "unanimous",
            "consensus_verdict": "hit",
            "reference_ledger_label": "hit",  # key agrees with panel
        },
        {
            "case_id": "Q",
            "student_id": "S1",
            "point_id": "P2",
            "blind_votes": {"a": "miss", "b": "miss", "c": "miss"},
            "route": "unanimous",
            "consensus_verdict": "miss",  # panel is unanimous (self-agreement high)
            "reference_ledger_label": "hit",  # but the OFFICIAL KEY says this point landed
        },
    ]
    return {
        "rows": rows,
        "aggregate": {"consensus_vs_reference_agreement": 0.5},
    }


def _original_scorecard() -> dict:
    """A minimal original scorecard mirroring the violation: quality_claim True on
    panel self-kappa, with structural axes that must survive the correction."""
    return {
        "schema_version": "luban_grading_verdict_ab.v1",
        "quality_claim_allowed": True,
        "gold_label_authority": "ai_arbitration_panel_candidate",
        "gold_fleiss_kappa": {
            "fleiss_kappa": 0.95,  # panel agrees with ITSELF strongly...
            "quality_claim_allowed": True,
            "label_authority": "ai_arbitration_panel_candidate",
        },
        "scorecards": [
            {
                "arm": "typed_case_grading_artifact_grader",
                "axis2_validator_pass_rate": 0.9167,
                "axis2_validator_rows": 12,
                "axis2_contract_enforced": True,
                "axis2_contract_enforced_rows": 1,
                "axis3_deduction_completeness": 1.0,
                "axis3_deduction_needed": 20,
                "axis4_tag_completeness": 1.0,
                "axis4_tag_distinct_per_emitted": 0.05,
                "axis5_evidence_completeness": 1.0,
                "axis5_evidence_needed": 27,
                "axis9_field_compliance_rate": 1.0,
            }
        ],
        "verdict_summary": {
            "interpretation": "typed_contract_arm_wins_on_auditability",
            "quality_claim_allowed": True,
            "directional_only": False,
        },
    }


def _arm_rows() -> dict:
    """An arm that perfectly matches the PANEL (so consensus-anchored accuracy looks
    perfect) but therefore MISSES the key on the disagreement point."""
    return {
        "typed_case_grading_artifact_grader": [
            {
                "case_id": "Q",
                "student_id": "S1",
                "validation_status": "passed",
                "point_results": [
                    {"point_id": "P1", "status": "hit"},
                    {"point_id": "P2", "status": "miss"},  # follows panel, but key says hit
                ],
            }
        ]
    }


def _build() -> dict:
    return corrector.build_corrected_scorecard(
        _original_scorecard(), _gold_panel(), _arm_rows()
    )


# --------------------------------------------------------------- discipline gates


def test_high_panel_self_kappa_disagreeing_with_key_blocks_quality_claim():
    """The core gate: panel self-agreement kappa is 0.95 (very high), but the panel
    diverges from the official key, so quality_claim_allowed MUST be False."""
    corrected = _build()
    assert corrected["quality_claim_allowed"] is False
    assert corrected["gold_fleiss_kappa"]["quality_claim_allowed"] is False
    assert corrected["gold_fleiss_kappa"]["fleiss_kappa"] == 0.95  # kappa value untouched...
    assert corrected["authority"]["panel_self_agreement_is_not_authority"] is True
    # ...but it is explicitly NOT the authority
    assert corrected["gold_label_authority"] == "official_answer_key"
    assert corrected["authority"]["single_authority"] == "official_answer_key"
    assert corrected["verdict_summary"]["quality_claim_allowed"] is False
    assert corrected["verdict_summary"]["directional_only"] is True


def test_accuracy_axes_anchor_to_official_key_not_consensus():
    """Accuracy must be measured against reference_ledger_label, not consensus_verdict.

    The arm matches the panel on both points -> consensus-anchored accuracy would be
    perfect. But the key disagrees on P2 (key=hit, arm=miss) -> key-anchored accuracy
    must show that miss."""
    corrected = _build()
    sc = corrected["scorecards"][0]
    assert sc["accuracy_anchor"] == "official_answer_key"
    # Key-anchored: arm missed a gold-hit point -> miss_rate > 0, exact < 1.0
    assert sc["axis6_miss_rate"] == 0.5  # 1 of 2 official-hit points missed
    assert sc["axis1_hit_concordance"]["exact_agreement"] == 0.5
    # The panel cross-check (NOT authority) would have looked perfect:
    pc = sc["panel_crosscheck_not_authority"]
    assert pc["anchor"] == "ai_panel_consensus_verdict"
    assert pc["axis1_hit_concordance"]["exact_agreement"] == 1.0  # perfect vs panel
    assert pc["axis6_miss_rate"] == 0.0
    # Key-anchored accuracy is strictly worse than panel-anchored -> proves re-anchor
    assert sc["axis1_hit_concordance"]["exact_agreement"] < pc["axis1_hit_concordance"]["exact_agreement"]


def test_panel_key_disagreement_becomes_review_candidate_not_override():
    """Where the panel disagrees with the key, it produces an owner-review candidate;
    the key label is preserved and never overridden."""
    corrected = _build()
    cands = corrected["owner_key_review_candidates"]
    assert corrected["owner_key_review_candidate_count"] == 1
    c = cands[0]
    assert c["point_id"] == "P2"
    assert c["official_answer_key_label"] == "hit"  # key preserved
    assert c["panel_consensus_verdict"] == "miss"  # panel disagreement recorded
    assert c["decision"] == "candidate_for_owner_review_key_not_overridden"


def test_structural_axes_are_preserved_verbatim():
    """Authority-agnostic structural axes (validator pass, deduction/tag/evidence
    completeness, schema compliance) must survive the re-anchor untouched."""
    corrected = _build()
    sc = corrected["scorecards"][0]
    assert sc["axis2_validator_pass_rate"] == 0.9167
    assert sc["axis2_contract_enforced"] is True
    assert sc["axis3_deduction_completeness"] == 1.0
    assert sc["axis5_evidence_completeness"] == 1.0
    assert sc["axis9_field_compliance_rate"] == 1.0
    # The typed-arm auditability conclusion still stands.
    assert corrected["verdict_summary"]["interpretation"] == "typed_contract_arm_wins_on_auditability"
    assert "structural_conclusion_preserved" in corrected["verdict_summary"]


def test_unmatched_points_recorded_honestly_not_guessed():
    """A gold row with no matching arm point, and an arm point with no gold row, are
    recorded as unmatched rather than silently coerced."""
    gold = _gold_panel()
    arm = {
        "typed_case_grading_artifact_grader": [
            {
                "case_id": "Q",
                "student_id": "S1",
                "validation_status": "passed",
                "point_results": [
                    {"point_id": "P1", "status": "hit"},
                    # P2 omitted -> unmatched gold point
                    {"point_id": "P9", "status": "hit"},  # no gold row -> unmatched arm point
                ],
            }
        ]
    }
    corrected = corrector.build_corrected_scorecard(_original_scorecard(), gold, arm)
    sc = corrected["scorecards"][0]
    assert "Q/S1/P9" in sc["unmatched_arm_points"]
    assert "Q/S1/P2" in sc["unmatched_gold_points"]


# --------------------------------------------------------------- landed-artifact e2e


def test_corrector_reanchors_landed_artifacts(tmp_path: Path):
    """End-to-end on a copy of the real landed artifacts: the corrected scorecard
    demotes the quality claim and re-anchors accuracy to the key, and the landed
    consensus-anchored numbers are demonstrably different from the key-anchored ones."""
    src = Path(
        "artifacts/luban_grading_artifacts/luban_grading_verdict_ab_20260613"
    )
    original = json.loads((src / "verdict_scorecard.json").read_text(encoding="utf-8"))
    gold_panel = json.loads((src / "gold_panel.json").read_text(encoding="utf-8"))
    arm_rows = json.loads((src / "arm_rows.json").read_text(encoding="utf-8"))["arm_rows"]

    # The landed (violating) original asserted the quality claim on panel self-kappa.
    assert original["quality_claim_allowed"] is True
    assert original["gold_label_authority"] == "ai_arbitration_panel_candidate"

    corrected = corrector.build_corrected_scorecard(original, gold_panel, arm_rows)
    assert corrected["quality_claim_allowed"] is False
    assert corrected["authority"]["single_authority"] == "official_answer_key"
    # 15.4% panel/key disagreement -> 6 review candidates on the real slice.
    assert corrected["owner_key_review_candidate_count"] == 6

    by_arm = {sc["arm"]: sc for sc in corrected["scorecards"]}
    typed = by_arm["typed_case_grading_artifact_grader"]
    # Key-anchored accuracy is worse than the panel cross-check (the inflation proof):
    key_qwk = typed["axis1_hit_concordance"]["qwk"]
    panel_qwk = typed["panel_crosscheck_not_authority"]["axis1_hit_concordance"]["qwk"]
    assert key_qwk < panel_qwk
    # Over-credit surfaces under the key (arms credited official-miss points).
    assert typed["axis7_overcredit_rate"] > 0.0
    # Structural axes preserved from the landed original.
    assert typed["axis2_validator_pass_rate"] == original["scorecards"][0]["axis2_validator_pass_rate"]
