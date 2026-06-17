"""Phase 16 — PO handoff: BLIND review sheet + hidden answer key + auto-scorer.

The PO sign-off is the ONE irreducible real-human anchor. To keep it non-circular it must be BLIND:
the reviewer must NOT see the AI verdict (else anchoring inflates agreement). So this splits the
114-item package into:
  * po_review_sheet.csv  — official answer + the one point + student answer + a BLANK 人工判定 column.
                           NO AI verdict shown. The teaching expert grades from scratch.
  * po_answer_key.json   — the AI gold verdicts, hidden from the reviewer, used only by the scorer.

After the expert fills 人工判定, run `score <filled.csv>` to compute the v1 verdict against the
acceptance protocol (deterministic, no judgment):
  * high-sample agreement >= 0.90  AND  no (case,verdict) stratum with >=50% disagreement
  * medium (arbitrated) agreement >= 0.80
  -> both pass => scaled gold promoted to v1 (PO sign-off). Else failing items/strata return to
    escalation; gold stays v0.9 candidate.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SG = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
          "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/scaled_gold")
HIGH_THRESH = 0.90
MED_THRESH = 0.80
STRATUM_FAIL = 0.50
NORM = {"命中": "hit", "部分": "partial", "未命中": "miss"}


def build():
    pkg = json.loads((SG / "po_sampling_package.json").read_text("utf-8"))["records"]
    rows = sorted(pkg, key=lambda r: (r["case_id"], r["student_id"], r["point_id"]))
    cols = ["row_id", "review_tier", "case_id", "student_id", "point_id", "max_score",
            "官方答案", "待判采分点", "学生作答", "人工判定_填hit_partial_miss", "人工备注"]
    with (SG / "po_review_sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(rows):
            w.writerow([i, r["review_tier"], r["case_id"], r["student_id"], r["point_id"], r["max_score"],
                        (r["official_answer"] or "").replace("\n", " "),
                        (r["point_label"] or "").replace("\n", " "),
                        (r["student_answer"] or "").replace("\n", " "), "", ""])
    key = {str(i): {"ai_gold_verdict": r["ai_gold_verdict"], "review_tier": r["review_tier"],
                    "case_id": r["case_id"], "point_id": r["point_id"]}
           for i, r in enumerate(rows)}
    (SG / "po_answer_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({"po_review_sheet": str(SG / "po_review_sheet.csv"),
                      "hidden_answer_key": str(SG / "po_answer_key.json"),
                      "n_items": len(rows), "blind": True,
                      "next": "教研/PO 填『人工判定』列 -> 跑 `python phase16_po_handoff.py score <filled.csv>`"},
                     ensure_ascii=False, indent=1))


def score(filled_csv):
    key = json.loads((SG / "po_answer_key.json").read_text("utf-8"))
    rows = list(csv.DictReader(Path(filled_csv).open(encoding="utf-8-sig")))
    by_tier = defaultdict(lambda: [0, 0])
    strat = defaultdict(lambda: [0, 0])
    unfilled = 0
    for r in rows:
        k = key.get(str(r.get("row_id")))
        if not k:
            continue
        ph = (r.get("人工判定_填hit_partial_miss") or "").strip().lower()
        ph = NORM.get(ph, ph)
        if ph not in ("hit", "partial", "miss"):
            unfilled += 1
            continue
        ai = k["ai_gold_verdict"]
        agree = ph == ai
        by_tier[k["review_tier"]][1] += 1
        by_tier[k["review_tier"]][0] += int(agree)
        s = (k["case_id"], ai)
        strat[s][1] += 1
        strat[s][0] += int(not agree)

    def rate(t):
        a, n = by_tier.get(t, [0, 0])
        return round(a / n, 4) if n else None

    high, med = rate("high_stratified_sample"), rate("medium_arbitrated_all")
    bad_strata = [{"stratum": list(k), "disagree": v[0], "total": v[1]}
                  for k, v in strat.items() if v[1] >= 2 and v[0] / v[1] >= STRATUM_FAIL]
    high_ok = high is not None and high >= HIGH_THRESH and not bad_strata
    med_ok = med is not None and med >= MED_THRESH
    verdict = {
        "high_sample_agreement": high, "high_threshold": HIGH_THRESH, "high_ok": high_ok,
        "medium_agreement": med, "medium_threshold": MED_THRESH, "medium_ok": med_ok,
        "systematic_failure_strata": bad_strata, "unfilled_rows": unfilled,
        "V1_SIGNOFF": bool(high_ok and med_ok),
        "decision": ("scaled gold -> v1 (PO 签通过)" if (high_ok and med_ok)
                     else "维持 v0.9 candidate;失败项/层退回 escalation 修正后重审"),
    }
    (SG / "po_signoff_result.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "score":
        score(sys.argv[2])
    else:
        build()
