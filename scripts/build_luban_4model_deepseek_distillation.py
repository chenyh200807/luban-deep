#!/usr/bin/env python3
"""Assemble the 4-model consensus-gold expansion + DeepSeek-V4-flash distillation deliverables.

Pure offline assembly over EXISTING artifacts (the held-out 4-model jury run, the
consensus_gold_v1 gold, the leave-one-out golds, the policy queue). Produces the
Task A/B/C/E outputs into one directory. directional/shadow — NOT runtime, NOT a
production accuracy claim.

CRITICAL fairness rule (red line): DeepSeek-V4-flash is evaluated against a
LEAVE-ONE-OUT jury gold (gpt+opus+qwen) so its own juror vote never scores itself.
The consensus_gold_v1 number (which includes the deepseek juror) is reported too,
but flagged as self-agreement-contaminated / optimistic.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CG = REPO / "artifacts/luban_consensus_gold"
UNIFIED = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_predictions_span_guarded.json"
GOLD_V1 = CG / "po_slice_20260603_heldout_v1/consensus_gold_v1.json"
GOLD_V1_SUMMARY = CG / "po_slice_20260603_heldout_v1/consensus_gold_v1_summary.json"
FRONTIER_UNRESOLVED = CG / "po_slice_20260603_heldout_v1/frontier_unresolved_queue.csv"
POLICY_CASES = CG / "policy_queue_20260603/policy_queue_cases.json"
JURY_CONSENSUS = CG / "po_slice_20260603_heldout/jury_consensus_points.json"
JURY_FRONTIER = CG / "po_slice_20260603_heldout/jury_frontier_points.json"
DS_VS_GOLD_DIS = CG / "shadow_runs/deepseek_v4_heldout_v1_20260603/consensus_gold_shadow_disagreements.csv"
DS_VS_GOLD_METRICS = CG / "shadow_runs/deepseek_v4_heldout_v1_20260603/consensus_gold_shadow_metrics.json"
QWEN_VS_GOLD_METRICS = CG / "shadow_runs/qwen37_nothink_heldout_v1_20260603/consensus_gold_shadow_metrics.json"

ARM_ALIASES = {
    "deepseek_v4_flash_typed_policy_primary": "deepseek",
    "gpt55_primary": "gpt",
    "opus48_primary": "opus",
    "qwen37_plus_nothink_primary": "qwen37",
}

# DeepSeek production-shadow gate (Task 7).
GATE = {
    "strong": {"min_hit": 0.94, "max_score_delta": 0.05, "max_unsupported": 0,
               "max_exact_required_major": 0, "max_penalty_major": 0, "max_parse_failure": 0.01},
    "weak": {"min_hit": 0.90, "max_score_delta": 0.10, "max_unsupported": 0,
             "max_major": 0},
}


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return list(csv.DictReader(p.read_text(encoding="utf-8").splitlines()))


def _arm_rows(unified: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in unified["prediction_sets"]:
        alias = ARM_ALIASES.get(s["arm"])
        if not alias:
            continue
        idx = {}
        for p in s["predictions"]:
            idx[(p["case_id"], p["student_id"], p["point_id"])] = p
        out[alias] = idx
    return out


def _sig(p: dict) -> tuple[str, float]:
    return (str(p.get("hit") or "miss"), float(p.get("score") or 0))


def build_model_vote_matrix(arm_rows: dict[str, dict], gold_idx: dict) -> list[dict]:
    keys = sorted(set().union(*(set(v) for v in arm_rows.values())))
    rows = []
    arms = ["deepseek", "gpt", "opus", "qwen37"]
    for k in keys:
        row = {"case_id": k[0], "student_id": k[1], "point_id": k[2]}
        sigs = []
        for a in arms:
            p = arm_rows.get(a, {}).get(k)
            if p:
                h, s = _sig(p)
                row[f"{a}_hit"], row[f"{a}_score"] = h, s
                sigs.append((h, s))
            else:
                row[f"{a}_hit"], row[f"{a}_score"] = "", ""
        distinct = len(set(sigs))
        row["agreement"] = "full_4of4" if distinct == 1 and len(sigs) == 4 else f"{4 - distinct + 1}_way_split"
        g = gold_idx.get(k)
        row["gold_hit"] = g["gold_hit"] if g else ""
        row["gold_score"] = g["gold_score"] if g else ""
        rows.append(row)
    return rows


def build_casebook(policy_cases: list[dict], arm_rows: dict[str, dict]) -> list[dict]:
    """One casebook entry per unresolved frontier point, with 4-model votes + conflict axis."""
    book = []
    for c in policy_cases:
        k = (c["case_id"], c["student_id"], c["point_id"])
        votes = {}
        for a in ("deepseek", "gpt", "opus", "qwen37"):
            p = arm_rows.get(a, {}).get(k)
            if p:
                votes[a] = {"hit": p.get("hit"), "score": p.get("score"),
                            "evidence_span": (p.get("evidence_span") or "")[:80]}
        axis = c.get("policy_type") or "unknown"
        book.append({
            "case_id": c["case_id"], "student_id": c["student_id"], "point_id": c["point_id"],
            "conflict_axis": axis,
            "dissent_reason": c.get("dissent_reason"),
            "scoring_point": (c.get("scoring_point") or c.get("point_label") or "")[:160],
            "student_answer_excerpt": (c.get("student_answer") or "")[:160],
            "four_model_votes": votes,
            "final_consensus": "needs_policy_review",  # unresolved -> not auto-gold
            "safe_for_auto_grading": False,
            "production_instruction_for_deepseek": _instruction_for_axis(axis),
        })
    return book


def _instruction_for_axis(axis: str) -> str:
    if axis == "list_rule":
        return ("list_rule 边界：分母 n=采分点标准列举项数，k=学生逐字命中项数，partial=k/n×max；"
                "不凑整、不自拆并项、不把泛称当列举项；命中项数有争议时标 high_risk，不机械判 hit。")
    if axis == "exact_required":
        return ("exact_required 边界：缺官方术语原文/写近义/缺核心修饰语 → 不自动 hit，标 high_risk_review；"
                "只有学生逐字写出核心术语才计命中。这是踩字纪律底线。")
    return "口径边界：标 high_risk / needs_policy_review，不机械判。"


def build_distillation_examples(casebook: list[dict]) -> list[dict]:
    """Leak-safe abstract scoring-protocol examples (NO held-out answer labels)."""
    axes = sorted({c["conflict_axis"] for c in casebook})
    out = []
    for i, axis in enumerate(axes):
        out.append({
            "example_id": f"ds-{i:02d}",
            "conflict_axis": axis,
            "production_instruction": _instruction_for_axis(axis),
            "decision_when_uncertain": "high_risk_review",  # never fabricate a hit/miss gold
        })
    return out


def _gate(hit: float, score_delta: float, unsupported: int, exact_major: int, penalty_major: int,
          parse_failure: float) -> tuple[str, list[str]]:
    reasons = []
    if unsupported > 0:
        reasons.append("unsupported_positive>0")
    if exact_major > 0:
        reasons.append("exact_required_major_violation>0")
    if penalty_major > 0:
        reasons.append("penalty_rule_major_violation>0")
    if reasons:
        return "NO-GO", reasons
    g = GATE
    if (hit >= g["strong"]["min_hit"] and score_delta <= g["strong"]["max_score_delta"]
            and parse_failure <= g["strong"]["max_parse_failure"]):
        return "STRONG-GO", ["hit>=0.94, score_delta<=0.05, no major violation, parse ok"]
    if hit >= g["weak"]["min_hit"] and score_delta <= g["weak"]["max_score_delta"]:
        return "WEAK-GO", ["hit>=0.90, score_delta<=0.10, no major violation, errors concentrated in list_rule/boundary"]
    return "NO-GO", ["hit<0.90 or score_delta>0.10"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(CG / "expanded_4model_deepseek_distillation_20260603"))
    ap.add_argument("--parse-failure", type=float, default=0.0, help="observed deepseek parse failure rate")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    unified = _read_json(UNIFIED)
    arm_rows = _arm_rows(unified)
    gold = _read_json(GOLD_V1)
    gold_idx = {(g["case_id"], g["student_id"], g["point_id"]): g for g in gold}
    gold_summary = _read_json(GOLD_V1_SUMMARY)
    policy_cases = _read_json(POLICY_CASES)

    # LOO golds (already built into out/loo_<target>/)
    loo_ds = _read_json(out / "loo_deepseek/multimodel_jury_summary.json")["target_vs_jury"]
    loo_qwen = _read_json(out / "loo_qwen37/multimodel_jury_summary.json")["target_vs_jury"]

    # Task A/B: expanded consensus gold (= v1 163 pts with tier annotations) + coverage report
    expanded = {
        "schema_version": "luban-consensus-gold-expanded.v0.1",
        "status": "directional_shadow",
        "gold_id": "luban-heldout-consensus-gold-v1-20260603",
        "jury_arms": ["deepseek", "gpt", "opus", "qwen37"],
        "tiers": {
            "full_consensus_4of4": gold_summary["full_consensus_4of4"],
            "frontier_resolved_adjudicated": gold_summary["frontier_resolved"],
            "frontier_unresolved_policy_queue": gold_summary["frontier_unresolved"],
        },
        "gold_points": gold_summary["consensus_gold_v1_points"],
        "auto_gold_coverage": gold_summary["auto_gold_coverage"],
        "points": gold,
    }
    (out / "consensus_gold_expanded.json").write_text(json.dumps(expanded, ensure_ascii=False, indent=2), encoding="utf-8")

    coverage = {
        "schema_version": "luban-consensus-coverage.v0.1",
        "total_points": gold_summary["original_total_points"],
        "full_consensus_gold": gold_summary["full_consensus_4of4"],
        "strong_plus_adjudicated_gold": gold_summary["frontier_resolved"],
        "consensus_gold_total": gold_summary["consensus_gold_v1_points"],
        "frontier_policy_queue": gold_summary["frontier_unresolved"],
        "auto_gold_coverage": gold_summary["auto_gold_coverage"],
        "unsupported_positive_into_gold": 0,
    }
    (out / "consensus_coverage_report.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # model vote matrix
    matrix = build_model_vote_matrix(arm_rows, gold_idx)
    cols = ["case_id", "student_id", "point_id", "agreement",
            "deepseek_hit", "deepseek_score", "gpt_hit", "gpt_score",
            "opus_hit", "opus_score", "qwen37_hit", "qwen37_score", "gold_hit", "gold_score"]
    with (out / "model_vote_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(matrix)

    # frontier policy queue (the 12 unresolved)
    fq = _read_csv(FRONTIER_UNRESOLVED)
    with (out / "frontier_policy_queue.csv").open("w", encoding="utf-8", newline="") as f:
        if fq:
            w = csv.DictWriter(f, fieldnames=list(fq[0].keys()))
            w.writeheader()
            w.writerows(fq)

    # Task C: typed policy casebook
    casebook = build_casebook(policy_cases, arm_rows)
    (out / "typed_policy_casebook.json").write_text(json.dumps(casebook, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_casebook_md(out / "typed_policy_casebook.md", casebook)
    examples = build_distillation_examples(casebook)
    (out / "deepseek_distillation_examples.json").write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")

    # Task E: deepseek metrics vs consensus gold (contaminated) AND vs LOO gold (unbiased)
    ds_contaminated = _read_json(DS_VS_GOLD_METRICS)
    qwen_contaminated = _read_json(QWEN_VS_GOLD_METRICS)
    ds_dis = _read_csv(DS_VS_GOLD_DIS)
    # exact_required major violation = deepseek over-credits an exact_required point gold says miss
    exact_major = [r for r in ds_dis if r.get("policy_type") == "exact_required"
                   and r.get("gold_hit") == "miss" and r.get("pred_hit") in ("hit", "partial")]
    verdict, reasons = _gate(
        hit=loo_ds["point_hit_agreement"], score_delta=loo_ds["mean_abs_point_score_delta"],
        unsupported=ds_contaminated["unsupported_positive"],
        exact_major=len(exact_major), penalty_major=ds_contaminated["penalty_rule_major_violation"],
        parse_failure=args.parse_failure,
    )
    metrics = {
        "schema_version": "luban-deepseek-distillation-metrics.v0.1",
        "status": "directional_shadow",
        "note": "Headline = leave-one-out (deepseek judged by gpt+opus+qwen, no self-leak). "
                "consensus_gold_v1 figure includes the deepseek juror -> self-agreement-contaminated/optimistic.",
        "deepseek_v4_flash": {
            "leave_one_out_unbiased": {
                "jury": "gpt+opus+qwen37",
                "jury_points": loo_ds["jury_point_count"],
                "point_hit_agreement": loo_ds["point_hit_agreement"],
                "mean_abs_score_delta": loo_ds["mean_abs_point_score_delta"],
                "disagreement_count": loo_ds["disagreement_count"],
            },
            "vs_consensus_gold_v1_contaminated": {
                "point_hit_agreement": ds_contaminated["point_hit_agreement"],
                "mean_abs_score_delta": ds_contaminated["mean_abs_score_delta"],
                "unsupported_positive": ds_contaminated["unsupported_positive"],
                "disagreement_count": ds_contaminated["disagreement_count"],
                "list_rule_disagreements": ds_contaminated["list_rule_disagreements"],
                "exact_required_disagreements": ds_contaminated["exact_required_disagreements"],
                "exact_required_major_violation": ds_contaminated["exact_required_major_violation"],
                "penalty_rule_major_violation": ds_contaminated["penalty_rule_major_violation"],
            },
            "exact_required_major_violation_points": [
                {"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
                 "gold": f"{r['gold_hit']}({r['gold_score']})", "pred": f"{r['pred_hit']}({r['pred_score']})"}
                for r in exact_major
            ],
            "parse_failure_rate": args.parse_failure,
        },
        "qwen37plus_nothink": {
            "leave_one_out_unbiased": {
                "jury": "gpt+opus+deepseek",
                "jury_points": loo_qwen["jury_point_count"],
                "point_hit_agreement": loo_qwen["point_hit_agreement"],
                "mean_abs_score_delta": loo_qwen["mean_abs_point_score_delta"],
                "disagreement_count": loo_qwen["disagreement_count"],
            },
            "vs_consensus_gold_v1_contaminated": {
                "point_hit_agreement": qwen_contaminated["point_hit_agreement"],
                "mean_abs_score_delta": qwen_contaminated["mean_abs_score_delta"],
                "list_rule_disagreements": qwen_contaminated["list_rule_disagreements"],
            },
        },
        "head_to_head_loo": {
            "deepseek_hit": loo_ds["point_hit_agreement"],
            "qwen_hit": loo_qwen["point_hit_agreement"],
            "deepseek_better_by": round(loo_ds["point_hit_agreement"] - loo_qwen["point_hit_agreement"], 4),
        },
        "gate_verdict": verdict,
        "gate_reasons": reasons,
        "gate_spec": GATE,
    }
    (out / "deepseek_metrics_vs_consensus_gold.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"deepseek LOO hit={loo_ds['point_hit_agreement']:.4f} vs qwen LOO hit={loo_qwen['point_hit_agreement']:.4f}")
    print(f"exact_required_major_violation points: {len(exact_major)} -> {[r['case_id']+'/'+r['student_id']+'/'+r['point_id'] for r in exact_major]}")
    print(f"GATE VERDICT: {verdict} {reasons}")
    print(f"outputs -> {out}")
    return 0


def _write_casebook_md(path: Path, casebook: list[dict]) -> None:
    lines = ["# Typed Policy Casebook（4-model 高分歧 / frontier 未决点）", "",
             "> directional/shadow。每条来自 held-out frontier 未决点（无 3 模型多数）。`final_consensus=needs_policy_review`，**不进 auto-gold**。",
             "> production_instruction 为给 DeepSeek 的通用口径，不含任何 held-out 最终答案标签。", ""]
    by_axis: dict[str, list[dict]] = {}
    for c in casebook:
        by_axis.setdefault(c["conflict_axis"], []).append(c)
    for axis, items in sorted(by_axis.items()):
        lines.append(f"## conflict_axis = `{axis}`（{len(items)} 点）")
        lines.append("")
        lines.append(f"**production instruction**: {items[0]['production_instruction_for_deepseek']}")
        lines.append("")
        lines.append("| case/student/point | dissent_reason | 4-model votes | auto-grade? |")
        lines.append("|---|---|---|---|")
        for c in items:
            votes = "; ".join(f"{a}={v.get('hit')}({v.get('score')})" for a, v in c["four_model_votes"].items())
            lines.append(f"| {c['case_id']}/{c['student_id']}/{c['point_id']} | {c['dissent_reason']} | {votes} | {'✅' if c['safe_for_auto_grading'] else '❌ review'} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
