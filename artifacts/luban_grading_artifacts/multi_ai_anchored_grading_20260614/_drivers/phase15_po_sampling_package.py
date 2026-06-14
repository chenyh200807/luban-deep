"""Phase 15 — PO stratified sampling package (human anchor saved to the knife's edge).

The design's honest residual: redline's real-human anchor isn't eliminated, only minimized. This
builds the package a PO/teaching-expert reviews to sign off the scaled gold as v1 — WITHOUT reading
all 485 points. They review only:
  * contested  (ensemble unresolved) — ALL (here 0; Opus resolved all)
  * medium     (Opus-arbitrated judgment calls)            — ALL (39)
  * high       (ensemble consensus)  — STRATIFIED SAMPLE (~12%, spread across cases & verdicts) to
                                       confirm the high tier is genuinely reliable, not rubber-stamped

Each record is human-friendly: official answer + point + student span + the AI verdict(s), and a
blank `po_verdict` / `po_agrees` to fill. Output JSON + flat CSV for spreadsheet review. The sample
is deterministic (no RNG): stride-select within each (case, gold-verdict) stratum.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
M = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
SG = M / "scaled_gold"
GOLD_V1 = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"


def main() -> int:
    gold = json.loads((SG / "scaled_gold.json").read_text("utf-8"))["gold"]
    gv = json.loads(GOLD_V1.read_text("utf-8"))
    # index point label + student answer
    plabel, sans, stem = {}, {}, {}
    for c in gv["cases"]:
        stem[c["case_id"]] = (c.get("stem") or "")[:300]
        for p in c.get("gold_scoring_points") or []:
            plabel[(c["case_id"], p["point_id"])] = {"label": p.get("label"), "official_basis": p.get("official_basis"),
                                                     "official_answer": (c.get("official_answer") or "")[:500]}
        for s in c.get("eval_samples") or []:
            sans[(c["case_id"], s["student_id"])] = s.get("answer_text", "")

    contested = [g for g in gold if g["confidence"] == "contested"]
    medium = [g for g in gold if g["confidence"] == "medium"]
    high = [g for g in gold if g["confidence"] == "high"]

    # stratified high sample: stride within (case, gold_verdict) strata, ~12%
    strata = defaultdict(list)
    for g in high:
        strata[(g["case_id"], g["gold_verdict"])].append(g)
    high_sample = []
    for key, items in strata.items():
        items = sorted(items, key=lambda x: (x["student_id"], x["point_id"]))
        take = max(1, round(len(items) * 0.12))
        stride = max(1, len(items) // take)
        high_sample.extend(items[::stride][:take])

    def to_record(g, tier_reason):
        meta = plabel.get((g["case_id"], g["point_id"]), {})
        return {
            "case_id": g["case_id"], "student_id": g["student_id"], "point_id": g["point_id"],
            "review_tier": tier_reason,
            "official_answer": meta.get("official_answer", ""),
            "point_label": meta.get("label", ""), "official_basis": meta.get("official_basis", ""),
            "student_answer": sans.get((g["case_id"], g["student_id"]), ""),
            "ai_votes": g["votes"], "ai_gold_verdict": g["gold_verdict"],
            "max_score": g["max_score"],
            "po_verdict": "", "po_agrees": "", "po_note": "",  # human fills
        }

    package = ([to_record(g, "contested_all") for g in contested]
               + [to_record(g, "medium_arbitrated_all") for g in medium]
               + [to_record(g, "high_stratified_sample") for g in high_sample])

    summary = {
        "schema": "luban_po_sampling_package.v1", "generated_at_date": "2026-06-14",
        "purpose": "PO 人类只审此包即可对 scaled gold 做 v1 签;不读全部 485 点",
        "total_gold_points": len(gold),
        "po_reviews": len(package),
        "reduction": f"{len(package)}/{len(gold)} = {round(100*len(package)/len(gold))}% of full gold",
        "breakdown": {"contested_all": len(contested), "medium_arbitrated_all": len(medium),
                      "high_stratified_sample": len(high_sample),
                      "high_total": len(high), "high_sample_pct": round(100 * len(high_sample) / max(1, len(high)), 1)},
        "signoff_protocol": "PO 填 po_verdict/po_agrees;接受条件=medium 一致率达阈值 + high 抽样无系统性错;"
                            "high 抽样若现系统性错→该 case/verdict 层退回 escalation。",
        "honest": "student answers synthetic; this gates the GOLD's reliability, real-traffic gold needs real student流量后再校。",
    }
    (SG / "po_sampling_package.json").write_text(
        json.dumps({"summary": summary, "records": package}, ensure_ascii=False, indent=1), "utf-8")
    # flat CSV for spreadsheet review
    cols = ["review_tier", "case_id", "student_id", "point_id", "max_score", "point_label",
            "official_basis", "official_answer", "student_answer", "ai_gold_verdict",
            "po_verdict", "po_agrees", "po_note"]
    with (SG / "po_sampling_package.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in package:
            w.writerow(r)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
