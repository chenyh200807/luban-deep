#!/usr/bin/env python3
"""A/B report for the AI-Draft full-100 dry-run vs reference gold + existing arms.

Reference = 4-model LOO consensus gold (deepseek-excluded; NON-HUMAN, clearly labeled).
Existing arms (artifact_first/baseline/rag) read from full_three_arms if present;
CaseGradingSkillKernel direct metrics are data_unavailable unless a metrics file exists
(we do NOT run the kernel here, and do NOT fabricate). directional/shadow.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from scripts.luban_grading_metrics import agreement_block, qwk_for_pairs  # noqa: E402

GOLD = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/loo_gold_485_flat.json"
PACKET = REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/unified_typed_policy_packet_485.json"
THREE_ARMS = REPO / "artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_184856.json"


def _read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _gold_index():
    if not GOLD.exists():
        return {}
    return {(g["case_id"], g["student_id"], g["point_id"]): g for g in _read(GOLD)}


def _ptype_index():
    if not PACKET.exists():
        return {}, {}
    pt, qmax = {}, {}
    for t in _read(PACKET)["tasks"]:
        qmax[(t["case_id"], t["student_id"])] = sum((sp.get("max_score") or 0) for sp in t["scoring_points"])
        for sp in t["scoring_points"]:
            pt[(t["case_id"], t["student_id"], sp["point_id"])] = {"policy_type": (sp.get("typed_policy") or {}).get("policy_type"), "max": sp.get("max_score") or 0}
    return pt, qmax


def _arm_block(pred_pairs, gold_pairs, scores, gold_scores, qkeys, qmax):
    """metrics for a set of (pred_hit, gold_hit) + scores vs gold."""
    blk = agreement_block(pred_pairs, gold_pairs)
    n = len(pred_pairs) or 1
    raw = round(sum(abs(s - g) for s, g in zip(scores, gold_scores)) / n, 4)
    npq = round(sum(abs(s - g) / (qmax.get(q) or 1) for s, g, q in zip(scores, gold_scores, qkeys)) / n, 4)
    return {**blk, "raw_score_delta": raw, "normalized_per_question_delta": npq}


def summarize(results_path: Path, out_dir: Path):
    data = _read(results_path)
    drafts = data.get("drafts", [])
    gold = _gold_index()
    pt, qmax = _ptype_index()

    # collect AI-Draft point rows joined to gold
    all_rows, cert_rows = [], []
    span_found = unsupported = high_risk = auto_cert = total_pts = parse_fail = 0
    by_type_rows = defaultdict(list)
    for d in drafts:
        if d.get("parse_status") != "ok":
            parse_fail += 1
        cid, sid = d.get("question_id"), d.get("student_id")
        for p in d.get("point_results", []):
            total_pts += 1
            k = (cid, sid, p.get("point_id"))
            if p.get("unsupported"):
                unsupported += 1
            else:
                # evidence_span found = positive with a non-empty span that passed guard
                if str(p.get("hit")) in ("hit", "partial") and (p.get("evidence_span") or "").strip():
                    span_found += 1
            if p.get("high_risk_review"):
                high_risk += 1
            if p.get("auto_certified"):
                auto_cert += 1
            g = gold.get(k)
            if g is None:
                continue
            row = {"k": k, "pred_hit": p.get("hit"), "gold_hit": g["gold_hit"],
                   "pred_score": float(p.get("score") or 0), "gold_score": float(g["gold_score"] or 0),
                   "policy_type": (pt.get(k) or {}).get("policy_type"), "auto_certified": bool(p.get("auto_certified"))}
            all_rows.append(row)
            by_type_rows[row["policy_type"]].append(row)
            if row["auto_certified"]:
                cert_rows.append(row)

    pos_denom = sum(1 for d in drafts for p in d.get("point_results", []) if str(p.get("hit")) in ("hit", "partial"))

    def block(rows):
        return _arm_block([r["pred_hit"] for r in rows], [r["gold_hit"] for r in rows],
                          [r["pred_score"] for r in rows], [r["gold_score"] for r in rows],
                          [(r["k"][0], r["k"][1]) for r in rows], qmax)

    report = {
        "reference": "4-model LOO consensus gold (deepseek-excluded) — NON-HUMAN reference, not a production accuracy claim",
        "sample_count": len(drafts), "point_count": total_pts,
        "points_with_gold": len(all_rows),
        "parse_failure_rate": round(parse_fail / (len(drafts) or 1), 4),
        "unsupported_positive_rate": round(unsupported / (total_pts or 1), 4),
        "evidence_span_found_rate": round(span_found / (pos_denom or 1), 4),
        "high_risk_review_rate": round(high_risk / (total_pts or 1), 4),
        "auto_certified_rate": round(auto_cert / (total_pts or 1), 4),
        "ai_draft_model_vs_gold": block(all_rows),
        "ai_draft_auto_certified_vs_gold": block(cert_rows),
        "by_policy_type": {str(t): block(rows) for t, rows in by_type_rows.items()},
        "token_cost_proxy": "unavailable (runner did not capture provider token usage this round)",
    }

    # existing arms (artifact_first/baseline/rag) — read if present, else data_unavailable
    if THREE_ARMS.exists():
        d3 = _read(THREE_ARMS)
        report["existing_arms_three_arms_summary"] = {
            "note": "from full_three_arms (ledger-anchored gold, different reference than 4-model LOO; magnitudes NOT directly comparable to AI-Draft's QWK)",
            "summary": d3.get("summary"),
        }
    else:
        report["existing_arms_three_arms_summary"] = "data_unavailable"
    report["case_grading_skill_kernel_metrics"] = "data_unavailable (kernel not run here; not fabricated)"

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ai_draft_ab_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_finding(out_dir / "FINDING_ai_draft_full100_ab_20260604.md", report, data)
    print(json.dumps({k: report[k] for k in ("sample_count", "point_count", "parse_failure_rate", "unsupported_positive_rate",
                                             "evidence_span_found_rate", "high_risk_review_rate", "auto_certified_rate")}, ensure_ascii=False, indent=2))
    print("model_vs_gold:", report["ai_draft_model_vs_gold"])
    print("auto_certified_vs_gold:", report["ai_draft_auto_certified_vs_gold"])
    return report


def _write_finding(path, r, data):
    md = r["ai_draft_model_vs_gold"]
    ac = r["ai_draft_auto_certified_vs_gold"]
    lines = [
        "# FINDING: AI-Draft full-100 dry-run A/B（2026-06-04）",
        "",
        "> status: `directional/shadow / candidate_only`。**dry_run（无写库）/ 不接 runtime / 不改 kernel / 不接 RAG / 不新增表 / QWK 非生产 gate / high_risk_review 不当正确。**",
        f"> reference = {r['reference']}。",
        "",
        "## 完成度 / 守卫",
        f"- sample_count={r['sample_count']} · point_count={r['point_count']}（有 gold 的点 {r['points_with_gold']}）",
        f"- parse_failure_rate={r['parse_failure_rate']} · unsupported_positive_rate={r['unsupported_positive_rate']} · evidence_span_found_rate={r['evidence_span_found_rate']}",
        f"- high_risk_review_rate={r['high_risk_review_rate']} · auto_certified_rate={r['auto_certified_rate']}",
        "",
        "## AI-Draft vs reference gold",
        "| 口径 | QWK | exact_agr | adj_agr | raw_score_delta | norm/question |",
        "|---|---:|---:|---:|---:|---:|",
        f"| model_draft（全点） | {md['qwk']} | {md['exact_agreement']} | {md['adjacent_agreement']} | {md['raw_score_delta']} | {md['normalized_per_question_delta']} |",
        f"| auto_certified（认证子集） | {ac['qwk']} | {ac['exact_agreement']} | {ac['adjacent_agreement']} | {ac['raw_score_delta']} | {ac['normalized_per_question_delta']} |",
        "",
        "## 按 policy_type（model_draft vs gold）",
        "| policy_type | points | QWK | raw_delta | norm/q |",
        "|---|---:|---:|---:|---:|",
    ]
    for t, b in r["by_policy_type"].items():
        lines.append(f"| {t} | {b['points']} | {b['qwk']} | {b['raw_score_delta']} | {b['normalized_per_question_delta']} |")
    lines += [
        "",
        "## 与现有 arms 对比",
        f"- existing three_arms（artifact_first/baseline/rag）: {'见 ai_draft_ab_metrics.json（ledger 锚定，与 4-model LOO 口径不同，量级不直接可比）' if r['existing_arms_three_arms_summary'] != 'data_unavailable' else 'data_unavailable'}",
        f"- CaseGradingSkillKernel 直评指标: {r['case_grading_skill_kernel_metrics']}",
        "- token/cost proxy: " + r["token_cost_proxy"],
        "",
        "## 边界",
        "- 非真人 gold；不宣称生产准确率。high_risk_review/unsupported 为待复核，不是 0 分、不是错误。",
        "- 仍 dry_run、不写 learner_memory_events、不接 harness router。",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    summarize(Path(args.input), Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
