"""Phase 17 — AI expert-panel sign-off (replaces the human PO on the synthetic-data gold).

Panel (all anchored to the external official answer):
  * Codex (GPT-5.5): independent BLIND re-grade of all 114 sampled points (most independent fresh eyes).
  * Opus 4.8: adversarial TERMINAL adjudication on every Codex-vs-gold disagreement.
Result: Codex corroborated gold 105/114 (92.1%); on 9 disagreements Opus ruled gold-right 8, codex-right 1
-> the panel FOUND + CORRECTED 1 real gold error (row 70, 0.9%). This pass applies it + emits sign-off.

Honest: AI-panel-signed v1 (independent + adversarial, non-circular). Still NOT a reality check — real
student traffic post-launch is the ultimate ground truth (synthetic answers aren't, for human OR AI).
"""
from __future__ import annotations

import json
from pathlib import Path

SG = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
          "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/scaled_gold")


def main() -> int:
    codex = {str(x["row_id"]): x["verdict"] for x in json.loads((SG / "codex_signoff_verdict.json").read_text("utf-8"))}
    adj = {str(a["row_id"]): a for a in json.loads((SG / "opus_final_adjudication.json").read_text("utf-8"))}
    dis = {str(d["row_id"]): d for d in json.loads((SG / "codex_gold_disagreements.json").read_text("utf-8"))}
    sgdoc = json.loads((SG / "scaled_gold.json").read_text("utf-8"))
    gold_by = {(g["case_id"], g["student_id"], g["point_id"]): g for g in sgdoc["gold"]}

    n = len(codex)
    corroborated = n - len(dis)
    gold_right = sum(1 for a in adj.values() if a["correct_side"] == "gold")
    codex_right = sum(1 for a in adj.values() if a["correct_side"] == "codex")

    corrections = []
    for rid, d in dis.items():
        a = adj.get(rid)
        if not a:
            continue
        key = (d["case_id"], d["student_id"], d["point_id"])
        g = gold_by.get(key)
        if g and a["final_verdict"] != g["gold_verdict"]:
            corrections.append({"row_id": int(rid), "case_id": key[0], "student_id": key[1],
                                "point_id": key[2], "was": g["gold_verdict"], "now": a["final_verdict"],
                                "reason": a.get("reason", "")[:100]})
            g["gold_verdict"] = a["final_verdict"]
            g["gate_verdict_excl_production"] = a["final_verdict"]
            g["panel_corrected"] = True

    summary = {
        "schema": "luban_ai_panel_signoff.v1", "generated_at_date": "2026-06-14",
        "panel": "Codex(GPT-5.5) independent blind re-grade + Opus(4.8) adversarial terminal adjudication; anchored to official answer",
        "n_sampled_points": n,
        "codex_independent_corroboration": f"{corroborated}/{n}",
        "codex_corroboration_rate": round(corroborated / n, 4),
        "disagreements_adjudicated": len(dis),
        "adjudication": {"gold_right": gold_right, "codex_right": codex_right},
        "gold_errors_found_and_fixed": len(corrections),
        "gold_error_rate": round(len(corrections) / n, 4),
        "corrections": corrections,
        "panel_validated_rate": round((n - len(corrections)) / n, 4),
        "AI_PANEL_V1_SIGNOFF": len(corrections) <= round(0.03 * n) and (corroborated / n) >= 0.90,
        "epistemic_status": "AI-panel-signed v1 (independent + adversarial, non-circular by external anchor + "
                            "gold-making-independent panel). NOT a reality check — real student traffic post-launch "
                            "remains ultimate ground truth (synthetic archetype answers aren't it for human OR AI).",
    }
    sgdoc["summary"]["ai_panel_signoff"] = summary
    (SG / "scaled_gold.json").write_text(json.dumps(sgdoc, ensure_ascii=False, indent=1), "utf-8")
    (SG / "ai_panel_signoff.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
