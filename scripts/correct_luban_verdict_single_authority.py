"""Offline single-authority re-anchoring of the Phase-3 grading verdict scorecard.

Background (single-authority violation):
``verdict_scorecard.json`` Phase-3 elevated the AI arbitration panel consensus
to gold authority (``quality_claim_allowed=True`` on the strength of the panel's
own Fleiss kappa 0.778, ``label_authority=ai_arbitration_panel_candidate``) and
measured the three grading arms against ``consensus_verdict`` -- even though the
panel disagrees with the official answer key on 15.4% of points.

Single-authority discipline: the official answer key (per-point textbook ledger,
landed as ``reference_ledger_label`` on each gold row) is the ONLY authority for
"did this scoring point land". The AI panel is a noise-reduction mirror and a
key-error candidate flagger -- never an authority, never an override of the key.

This module is a PURE OFFLINE re-derivation. It reads the already-landed
artifacts (``gold_panel.json`` + ``arm_rows.json``); it makes NO LLM / provider
call. It re-anchors the accuracy axes (axis 1/6/7/8) to the official key, keeps
the structural axes (axis 2/3/4/5/9 -- validator pass, deduction / tag / evidence
completeness, schema compliance) untouched because they are authority-agnostic,
demotes ``quality_claim_allowed`` to False, and exports the panel/key
disagreements as ``owner_key_review_candidates`` (candidates only -- the key is
never rewritten).

The corrected scorecard is written to a NEW file
``verdict_scorecard_single_authority_corrected.json`` so the original is
preserved for audit comparison.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import luban_grading_metrics as metrics  # noqa: E402

# The single authority. NEVER consensus_verdict.
AUTHORITY_FIELD = "reference_ledger_label"
PANEL_CROSSCHECK_FIELD = "consensus_verdict"

_ORD = {"miss": 0, "partial": 1, "hit": 2}


def _ord(status: str) -> int:
    return _ORD.get(str(status or "").lower(), 0)


def _gold_by_key(gold_panel: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, str]]:
    """Index gold rows by (case_id, student_id, point_id) -> {authority, panel}."""
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in gold_panel["rows"]:
        key = (str(row["case_id"]), str(row["student_id"]), str(row["point_id"]))
        out[key] = {
            "authority": str(row[AUTHORITY_FIELD]),
            "panel": str(row[PANEL_CROSSCHECK_FIELD]),
        }
    return out


def _join_arm(
    arm_rows: list[dict[str, Any]],
    gold: dict[tuple[str, str, str], dict[str, str]],
    anchor: str,
) -> dict[str, Any]:
    """Join one arm's point_results to gold rows on (case,student,point).

    Returns the re-anchored accuracy axes plus honest unmatched bookkeeping.
    ``anchor`` is either "authority" (official key) or "panel" (cross-check only).
    """
    pred_hits: list[str] = []
    gold_hits: list[str] = []
    abs_err: list[int] = []
    miss_when_gold_hit = 0
    gold_hit_total = 0
    overcredit_when_gold_miss = 0
    gold_miss_total = 0
    matched = 0
    unmatched_arm_points: list[str] = []  # arm emitted, no gold row
    seen_keys: set[tuple[str, str, str]] = set()

    for row in arm_rows:
        case_id = str(row.get("case_id"))
        student_id = str(row.get("student_id"))
        for pr in row.get("point_results") or []:
            point_id = str(pr.get("point_id"))
            key = (case_id, student_id, point_id)
            ref = gold.get(key)
            if ref is None:
                unmatched_arm_points.append("/".join(key))
                continue
            seen_keys.add(key)
            matched += 1
            gv = ref[anchor]
            av = str(pr.get("status") or "").lower()
            gold_hits.append(gv)
            pred_hits.append(av)
            abs_err.append(abs(_ord(av) - _ord(gv)))
            if gv == "hit":
                gold_hit_total += 1
                if av == "miss":
                    miss_when_gold_hit += 1
            if gv == "miss":
                gold_miss_total += 1
                if av == "hit":
                    overcredit_when_gold_miss += 1

    unmatched_gold_keys = [
        "/".join(k) for k in gold if k not in seen_keys
    ]  # gold row that no arm point covered
    n = len(gold_hits)

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    return {
        "anchor": anchor,
        "compared_point_count": n,
        "axis1_hit_concordance": metrics.agreement_block(pred_hits, gold_hits) if n else None,
        "axis6_miss_rate": rate(miss_when_gold_hit, gold_hit_total),
        "axis6_gold_hit_total": gold_hit_total,
        "axis7_overcredit_rate": rate(overcredit_when_gold_miss, gold_miss_total),
        "axis7_gold_miss_total": gold_miss_total,
        "axis8_ordinal_mae": round(sum(abs_err) / n, 4) if n else None,
        "unmatched_arm_points": sorted(unmatched_arm_points),
        "unmatched_gold_points": sorted(unmatched_gold_keys),
    }


def _owner_key_review_candidates(gold_panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Points where the panel consensus differs from the official key.

    These are CANDIDATES for a human key owner to review -- the panel flags a
    possible key error. The key is authoritative and is NOT changed here.
    """
    candidates: list[dict[str, Any]] = []
    for row in gold_panel["rows"]:
        if row[PANEL_CROSSCHECK_FIELD] != row[AUTHORITY_FIELD]:
            candidates.append(
                {
                    "case_id": row["case_id"],
                    "student_id": row["student_id"],
                    "point_id": row["point_id"],
                    "official_answer_key_label": row[AUTHORITY_FIELD],
                    "panel_consensus_verdict": row[PANEL_CROSSCHECK_FIELD],
                    "route": row.get("route"),
                    "blind_votes": row.get("blind_votes"),
                    "decision": "candidate_for_owner_review_key_not_overridden",
                }
            )
    return candidates


def build_corrected_scorecard(
    original: dict[str, Any],
    gold_panel: dict[str, Any],
    arm_rows_by_arm: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    gold = _gold_by_key(gold_panel)
    candidates = _owner_key_review_candidates(gold_panel)
    panel_self_kappa = float(original["gold_fleiss_kappa"]["fleiss_kappa"])
    panel_vs_reference_agreement = float(
        gold_panel["aggregate"]["consensus_vs_reference_agreement"]
    )

    # Build the original structural axes lookup (authority-agnostic; preserved verbatim).
    orig_by_arm = {sc["arm"]: sc for sc in original["scorecards"]}

    corrected_scorecards: list[dict[str, Any]] = []
    for arm, rows in arm_rows_by_arm.items():
        vs_key = _join_arm(rows, gold, "authority")
        vs_panel = _join_arm(rows, gold, "panel")
        orig = orig_by_arm.get(arm, {})
        corrected_scorecards.append(
            {
                "arm": arm,
                "compared_point_count": vs_key["compared_point_count"],
                # --- ACCURACY AXES re-anchored to the official answer key (SINGLE AUTHORITY) ---
                "axis1_hit_concordance": vs_key["axis1_hit_concordance"],
                "axis6_miss_rate": vs_key["axis6_miss_rate"],
                "axis6_gold_hit_total": vs_key["axis6_gold_hit_total"],
                "axis7_overcredit_rate": vs_key["axis7_overcredit_rate"],
                "axis7_gold_miss_total": vs_key["axis7_gold_miss_total"],
                "axis8_ordinal_mae": vs_key["axis8_ordinal_mae"],
                "accuracy_anchor": "official_answer_key",
                "unmatched_arm_points": vs_key["unmatched_arm_points"],
                "unmatched_gold_points": vs_key["unmatched_gold_points"],
                # --- STRUCTURAL AXES preserved (authority-agnostic) ---
                "axis2_validator_pass_rate": orig.get("axis2_validator_pass_rate"),
                "axis2_validator_rows": orig.get("axis2_validator_rows"),
                "axis2_contract_enforced": orig.get("axis2_contract_enforced"),
                "axis2_contract_enforced_rows": orig.get("axis2_contract_enforced_rows"),
                "axis3_deduction_completeness": orig.get("axis3_deduction_completeness"),
                "axis3_deduction_needed": orig.get("axis3_deduction_needed"),
                "axis4_tag_completeness": orig.get("axis4_tag_completeness"),
                "axis4_tag_distinct_per_emitted": orig.get("axis4_tag_distinct_per_emitted"),
                "axis5_evidence_completeness": orig.get("axis5_evidence_completeness"),
                "axis5_evidence_needed": orig.get("axis5_evidence_needed"),
                "axis9_field_compliance_rate": orig.get("axis9_field_compliance_rate"),
                # --- second-row cross-check ONLY (panel consensus is NOT authority) ---
                "panel_crosscheck_not_authority": {
                    "anchor": "ai_panel_consensus_verdict",
                    "axis1_hit_concordance": vs_panel["axis1_hit_concordance"],
                    "axis6_miss_rate": vs_panel["axis6_miss_rate"],
                    "axis7_overcredit_rate": vs_panel["axis7_overcredit_rate"],
                    "axis8_ordinal_mae": vs_panel["axis8_ordinal_mae"],
                    "note": "shown for noise-reduction diagnostics; never used to grant a quality claim",
                },
            }
        )

    corrected = dict(original)
    corrected["schema_version"] = "luban_grading_verdict_ab_single_authority_corrected.v1"
    corrected["authority"] = {
        "single_authority": "official_answer_key",
        "authority_field": AUTHORITY_FIELD,
        "panel_role": "noise_reduction_and_flagging_only",
        "panel_self_agreement_is_not_authority": True,
        "panel_self_fleiss_kappa": panel_self_kappa,
        "panel_vs_official_key_agreement": panel_vs_reference_agreement,
        "panel_vs_official_key_disagreement": round(1.0 - panel_vs_reference_agreement, 4),
    }
    # Demote the quality claim everywhere it was asserted.
    corrected["quality_claim_allowed"] = False
    corrected["gold_label_authority"] = "official_answer_key"
    corrected["gold_fleiss_kappa"] = dict(original["gold_fleiss_kappa"])
    corrected["gold_fleiss_kappa"]["quality_claim_allowed"] = False
    corrected["gold_fleiss_kappa"]["label_authority"] = "official_answer_key"
    corrected["gold_fleiss_kappa"]["note"] = (
        "panel self-agreement kappa is high but the panel diverges from the official "
        "key on "
        f"{round((1.0 - panel_vs_reference_agreement) * 100, 1)}% of points; panel "
        "agreement alone cannot grant a quality claim under single-authority discipline"
    )
    corrected["scorecards"] = corrected_scorecards
    corrected["owner_key_review_candidates"] = candidates
    corrected["owner_key_review_candidate_count"] = len(candidates)

    # Re-state the verdict summary honestly: structural conclusion survives, accuracy
    # claim is demoted to directional.
    orig_summary = dict(original.get("verdict_summary") or {})
    orig_summary["quality_claim_allowed"] = False
    orig_summary["directional_only"] = True
    orig_summary["accuracy_axes_reanchored_to"] = "official_answer_key"
    orig_summary["structural_conclusion_preserved"] = (
        "typed_contract_arm_wins_on_auditability remains valid; axis2/3/4/5/9 are "
        "authority-agnostic and unchanged"
    )
    corrected["verdict_summary"] = orig_summary

    corrected["correction_note"] = {
        "corrected_on": "2026-06-13",
        "method": "pure_offline_reaggregation_no_llm_no_provider_call",
        "reanchored_axes": [
            "axis1_hit_concordance",
            "axis6_miss_rate",
            "axis7_overcredit_rate",
            "axis8_ordinal_mae",
        ],
        "reanchored_from": "ai_panel_consensus_verdict",
        "reanchored_to": "official_answer_key (reference_ledger_label)",
        "preserved_axes": [
            "axis2_validator_pass_rate",
            "axis3_deduction_completeness",
            "axis4_tag_completeness",
            "axis5_evidence_completeness",
            "axis9_field_compliance_rate",
        ],
        "preserved_reason": "structural axes measure arm output schema/contract conformance, independent of label authority",
        "quality_claim_demoted_reason": (
            "Phase-3 granted quality_claim_allowed=True from the panel's own Fleiss "
            f"kappa ({panel_self_kappa}); but the panel disagrees with the official "
            f"answer key on {round((1.0 - panel_vs_reference_agreement) * 100, 1)}% of "
            "points. Panel self-consistency is not authority. Under single-authority "
            "discipline the only quality anchor is the official key, against which the "
            "accuracy is lower than the consensus-anchored numbers implied, so no "
            "quality claim is allowed."
        ),
        "preserved_original_file": "verdict_scorecard.json",
    }
    return corrected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        default="artifacts/luban_grading_artifacts/luban_grading_verdict_ab_20260613",
        help="directory holding verdict_scorecard.json, gold_panel.json, arm_rows.json",
    )
    args = parser.parse_args(argv)
    base = Path(args.artifact_dir)

    original = json.loads((base / "verdict_scorecard.json").read_text(encoding="utf-8"))
    gold_panel = json.loads((base / "gold_panel.json").read_text(encoding="utf-8"))
    arm_rows_by_arm = json.loads((base / "arm_rows.json").read_text(encoding="utf-8"))["arm_rows"]

    corrected = build_corrected_scorecard(original, gold_panel, arm_rows_by_arm)
    out_path = base / "verdict_scorecard_single_authority_corrected.json"
    out_path.write_text(
        json.dumps(corrected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_path}")
    print(f"quality_claim_allowed: {corrected['quality_claim_allowed']}")
    print(f"owner_key_review_candidate_count: {corrected['owner_key_review_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
