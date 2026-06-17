"""Phase 10 — non-circular offline regression of the coverage grading vs HUMAN gold.

The migration plan's Stage-4 gate wants MAE-not-worse vs legacy anchored to an INDEPENDENT
ledger. The repo's `luban_case_grading_golden_v1.json` is, by its own redline, AI-constructed
("两者皆AI,非AI-vs-人类真相; PO抽查为唯一人类锚; 顶级IRR=v1待真人") — grading AI coverage
against an AI gold would be CIRCULAR (the false-green the plan + eval-design warn against).

So this uses the ONE genuinely-human gold we have: the po_slice 131 human point-labels
(`po_labels_filled.csv`, used in Phase 1), 24 (case,student) pairs, ALL fully point-covered.
It decomposes the awarded-score error so the result is interpretable AND feeds owner decision #2:

  human_awarded      = Σ human per-point score                 (the true human total)
  human_uniform      = official_total × human_credited/total   (human verdicts, UNIFORM arithmetic)
  new_uniform        = official_total × AI_consensus_credited/total  (AI verdicts, UNIFORM arithmetic)

  MAE(new_uniform vs human_uniform)  = pure VERDICT error (AI vs human hit/miss)
  MAE(human_uniform vs human_awarded)= pure ARITHMETIC error (uniform coverage vs human's real scoring
                                       — this quantifies decision #2: does uniform mis-grade?)
  MAE(new_uniform vs human_awarded)  = end-to-end (what production would actually be off by)

HONEST BOUNDARY: 12 cases / 24 pairs is small + directional; a production Stage-4 gate needs
human gold at scale (PO sign-off / v1-真人, pending) AND a fair legacy arm. This is the precursor.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

M = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
         "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614")
PK = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
          "/artifacts/luban_human_validation_v1/po_slice_20260601/po_review_packet.json")


def _credit(verdict: str) -> float:
    v = (verdict or "").lower()
    return 1.0 if v == "hit" else (0.5 if v == "partial" else 0.0)


def main() -> int:
    rows = json.loads((M / "phase1_blind_grader_results.json").read_text("utf-8"))["rows"]
    pk = json.loads(PK.read_text("utf-8"))
    meta = {c["case_id"]: {"total": len(c.get("gold_scoring_points") or []),
                           "official_total": float(c.get("max_score") or 0)} for c in pk["cases"]}

    cs = defaultdict(list)
    for r in rows:
        cs[(r["case_id"], r["student_id"])].append(r)

    recs = []
    for (cid, sid), rs in cs.items():
        m = meta.get(cid)
        if not m or not m["total"] or not m["official_total"]:
            continue
        tot, oc = m["total"], m["official_total"]
        human_awarded = sum(float(r.get("human_score") or 0) for r in rs)
        human_cred = sum(_credit(r.get("human_hit")) for r in rs)
        # AI consensus credit: where DeepSeek & Qwen agree use it, else average the two
        ai_cred = 0.0
        for r in rs:
            dv, qv = r["deepseek"]["verdict"], r["dashscope"]["verdict"]
            ai_cred += _credit(dv) if _credit(dv) == _credit(qv) else (_credit(dv) + _credit(qv)) / 2
        human_uniform = oc * human_cred / tot
        new_uniform = oc * ai_cred / tot
        recs.append({"case": cid, "student": sid, "official_total": oc, "n_points": tot,
                     "human_awarded": round(human_awarded, 3),
                     "human_uniform": round(human_uniform, 3),
                     "new_uniform": round(new_uniform, 3)})

    def mae(a, b):
        return round(statistics.mean(abs(r[a] - r[b]) for r in recs), 4)

    n = len(recs)
    verdict_err = mae("new_uniform", "human_uniform")
    arithmetic_err = mae("human_uniform", "human_awarded")
    end_to_end = mae("new_uniform", "human_awarded")
    # normalize by mean official_total for an interpretable %
    mean_total = statistics.mean(r["official_total"] for r in recs)
    summary = {
        "schema": "luban_offline_human_gold_regression.v1", "generated_at_date": "2026-06-14",
        "gold": "po_slice 131 HUMAN point-labels (non-circular); NOT the AI-constructed golden_v1",
        "n_case_student_pairs": n, "mean_official_total": round(mean_total, 2),
        "MAE_verdict_error_new_vs_human_uniform": verdict_err,
        "MAE_arithmetic_error_uniform_vs_human_real": arithmetic_err,
        "MAE_end_to_end_new_vs_human_awarded": end_to_end,
        "as_pct_of_mean_total": {
            "verdict": round(100 * verdict_err / mean_total, 1),
            "arithmetic_decision2_evidence": round(100 * arithmetic_err / mean_total, 1),
            "end_to_end": round(100 * end_to_end / mean_total, 1),
        },
        "interpretation": {
            "verdict": "AI consensus 判分(命中/漏) 对人工的误差",
            "arithmetic_decision2": "均权 coverage 对人工真实给分的算术误差——decision#2 证据:大=阈值感知值得,小=均权够用",
            "end_to_end": "生产用 AI+均权 实际会偏离人工多少",
        },
        "honest_boundary": "12 cases/24 pairs 小样本+directional;Stage-4 生产门需规模化人工gold(PO/v1真人pending)+公平legacy臂;"
                           "golden_v1 是AI构造(其redline自承非人类真相)不能当门。",
    }
    (M / "phase5_factory" / "offline_human_gold_regression.json").write_text(
        json.dumps({"summary": summary, "records": recs}, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
