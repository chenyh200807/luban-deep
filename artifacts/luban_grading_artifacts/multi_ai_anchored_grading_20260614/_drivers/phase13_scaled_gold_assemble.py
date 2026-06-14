"""Phase 13 — assemble the scaled non-circular gold + validate vs the 131 human labels.

Stratified per the design: consensus → high; Opus-arbitrated → medium; (no contested — Opus resolved
all 39). Records every model vote so the GATE-TIME gold verdict can exclude the production model
(deepseek-chat). Final human-anchored validation: the subset overlapping po_slice's 131 HUMAN labels
must still match human — the proof the scaled gold is a valid non-circular human proxy.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
M = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"
SG = M / "scaled_gold"


def main() -> int:
    A = json.loads((SG / "stageA_propose.json").read_text("utf-8"))["rows"]
    opus = {(o["case_id"], o["student_id"], o["point_id"]): o
            for o in json.loads((SG / "stageB_opus_verdict.json").read_text("utf-8"))}

    gold = []
    for r in A:
        key = (r["case_id"], r["student_id"], r["point_id"])
        votes = {"deepseek": r["deepseek"], "qwen": r["dashscope"]}
        if r["agree"]:
            final, tier = r["deepseek"], "high"
        elif key in opus:
            ov = opus[key]["opus_verdict"]
            votes["opus"] = ov
            final, tier = ov, "medium"
        else:
            final, tier = "contested", "contested"
        # gate verdict EXCLUDING production model (deepseek): qwen, plus opus if present
        non_prod = [v for k, v in votes.items() if k != "deepseek" and v in ("hit", "partial", "miss")]
        if not non_prod:
            gate_verdict = "contested"
        elif "opus" in votes and votes["opus"] in ("hit", "partial", "miss"):
            gate_verdict = votes["opus"]  # arbiter authoritative among non-prod
        else:
            gate_verdict = non_prod[0]  # qwen for consensus
        gold.append({"case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
                     "max_score": r["max_score"], "votes": votes,
                     "gold_verdict": final, "gate_verdict_excl_production": gate_verdict, "confidence": tier})

    n = len(gold)
    tiers = {}
    for g in gold:
        tiers[g["confidence"]] = tiers.get(g["confidence"], 0) + 1

    # ---- validate vs po_slice 131 HUMAN labels (overlap) ----
    human = {}
    ph1 = json.loads((M / "phase1_blind_grader_results.json").read_text("utf-8"))["rows"]
    for r in ph1:
        hv = r["human_hit"]
        hv = "hit" if hv == "hit" else ("partial" if hv == "partial" else "miss")
        human[(r["case_id"], r["student_id"], r["point_id"])] = hv
    overlap = [g for g in gold if (g["case_id"], g["student_id"], g["point_id"]) in human]
    if overlap:
        gold_h = sum(1 for g in overlap
                     if g["gold_verdict"] == human[(g["case_id"], g["student_id"], g["point_id"])])
        gate_h = sum(1 for g in overlap
                     if g["gate_verdict_excl_production"] == human[(g["case_id"], g["student_id"], g["point_id"])])
        val = {"overlap_points": len(overlap),
               "scaled_gold_vs_human": round(gold_h / len(overlap), 4),
               "production_excluded_gate_gold_vs_human": round(gate_h / len(overlap), 4)}
    else:
        val = {"overlap_points": 0, "note": "golden_v1 cases do not overlap po_slice human labels by id"}

    summary = {
        "schema": "luban_scaled_gold.v1", "generated_at_date": "2026-06-14",
        "n_point_gold": n, "n_pairs": len({(g["case_id"], g["student_id"]) for g in gold}),
        "confidence_tiers": tiers,
        "human_validation_on_overlap": val,
        "non_circular": "gate_verdict_excl_production excludes deepseek-chat (production grader); anchored to official answer.",
        "honest_boundary": "student answers are synthetic archetypes (not real students); high+medium gold for gate, "
                           "PO human spot-check still needed on a stratified sample for v1 sign-off.",
    }
    (SG / "scaled_gold.json").write_text(
        json.dumps({"summary": summary, "gold": gold}, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
