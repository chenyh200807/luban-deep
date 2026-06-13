"""Phase 5 — assemble the full-bank candidate compilation + FINAL deterministic verification.

Merges the three resolution lanes into one candidate set and RE-VERIFIES every segment with the
deterministic must-not-mint guard (汉字 contiguous substring of the official answer) — trusting
no model self-report, including Opus's. Reports the real point-count lift vs the pre-factory
state (deterministic compiler alone: mean 2.69 pts/q, 91/179 collapsed to ≤1 point).

  lane A consensus       (81): both proposers agreed, no arbiter
  lane B deterministic   (10): type-rule tie-break on count-only disagreement
  lane C opus arbiter    (88): type disagreement / minting → Opus canonical

REVIEW-ONLY candidate. No production write. Human/adversarial sign-off still gates production.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
            "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory")
CASES = ROOT / "propose_by_case"
STAGE2 = ROOT / "stage2"
OUT = ROOT


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def _official_by_case() -> dict:
    m = {}
    for f in glob.glob(str(CASES / "*.json")):
        d = json.loads(Path(f).read_text("utf-8"))
        if "official_answer" in d:
            m[d["case_file"]] = d["official_answer"]
    return m


def _verify(segments: list[dict], oa: str) -> dict:
    oa_h = _hanzi(oa)
    minted = [s.get("text", "")[:30] for s in segments
              if _hanzi(s.get("text", "")) and _hanzi(s.get("text", "")) not in oa_h]
    return {"n": len(segments), "must_not_mint_ok": not minted, "minted": minted}


def main() -> int:
    official = _official_by_case()
    assembled = []

    consensus = json.loads((STAGE2 / "resolved_consensus.json").read_text("utf-8"))
    deterministic = json.loads((STAGE2 / "resolved_deterministic.json").read_text("utf-8"))
    for rec in consensus:
        rec["resolution_lane"] = "A_consensus"
        assembled.append(rec)
    for rec in deterministic:
        rec["resolution_lane"] = "B_deterministic_tiebreak"
        assembled.append(rec)
    for vf in sorted(glob.glob(str(STAGE2 / "opus_verdicts" / "*.json"))):
        for rec in json.loads(Path(vf).read_text("utf-8")):
            rec["resolution_lane"] = "C_opus_arbiter"
            assembled.append(rec)

    # FINAL deterministic must-not-mint verification on EVERY case (trust nothing)
    clean = 0
    violations = []
    total_points = 0
    type_dist = {}
    lane_dist = {}
    pts_per_q = []
    for rec in assembled:
        cf = rec.get("case_file")
        oa = official.get(cf, "")
        segs = rec.get("segments") or []
        v = _verify(segs, oa)
        rec["final_mnm_ok"] = v["must_not_mint_ok"]
        if v["must_not_mint_ok"]:
            clean += 1
        else:
            violations.append({"case_file": cf, "lane": rec["resolution_lane"], "minted": v["minted"]})
        total_points += v["n"]
        pts_per_q.append(v["n"])
        t = rec.get("point_type", "?")
        type_dist[t] = type_dist.get(t, 0) + 1
        lane_dist[rec["resolution_lane"]] = lane_dist.get(rec["resolution_lane"], 0) + 1

    n = len(assembled)
    collapsed_after = sum(1 for p in pts_per_q if p <= 1)
    summary = {
        "schema": "luban_full_factory_candidate.v1", "generated_at_date": "2026-06-14",
        "classification": {"candidate_only": True, "review_only": True,
                           "production_gated_by": "human/adversarial sign-off + migration plan stages"},
        "n_cases": n,
        "final_must_not_mint_clean": f"{clean}/{n}",
        "must_not_mint_violations": violations,
        "total_scoring_points": total_points,
        "mean_points_per_q": round(total_points / n, 2) if n else 0,
        "collapsed_to_le1_after": f"{collapsed_after}/{n}",
        "point_type_distribution": dict(sorted(type_dist.items())),
        "resolution_lane_distribution": lane_dist,
        "lift_vs_pre_factory": {
            "before_mean_pts_per_q": 2.69, "after_mean_pts_per_q": round(total_points / n, 2) if n else 0,
            "before_collapsed_le1": "91/179", "after_collapsed_le1": f"{collapsed_after}/{n}",
            "note": "before = deterministic compiler alone (splitter fail-closed on prose); "
                    "after = + multi-AI type-conditioned segmentation/authoring (Opus-arbitrated)",
        },
    }
    (OUT / "full_factory_candidate.json").write_text(
        json.dumps({"summary": summary, "cases": assembled}, ensure_ascii=False, indent=1), "utf-8")
    (OUT / "full_factory_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
