"""Phase 5 STAGE 2 prep — cost-aware split of the 98 needs_arbiter cases.

Two buckets:
  * count_only (type agreed, only segment-count differs): resolve DETERMINISTICALLY using the
    pilot's proven rule — point_type fixes granularity (list/enumeration → finer/more atomic;
    flaw_correction/process/single → coarser/keep complete statements). No Opus spend.
  * opus_cohort (type disagreement OR must-not-mint failure): genuinely needs the Opus arbiter
    (judgment on type + fixing minted segments). Written into batches for parallel Opus subagents.

Also passes through the 81 already-consensus cases (no arbiter needed) unchanged.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
            "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory")
CASES = ROOT / "propose_by_case"
OUT = ROOT / "stage2"
BATCHES = OUT / "opus_batches"

# point_types whose correct granularity is FINER (atomize each parallel item)
_FINE = {"list"}
# point_types whose correct granularity is COARSER (keep complete statements/pairs)
_COARSE = {"flaw_correction", "process", "single", "calculation"}


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def _mnm_ok(segments: list[dict], oa: str) -> bool:
    oa_h = _hanzi(oa)
    return all(_hanzi(s.get("text", "")) in oa_h for s in segments if _hanzi(s.get("text", "")))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    BATCHES.mkdir(parents=True, exist_ok=True)
    consensus, deterministic, opus = [], [], []

    for f in sorted(glob.glob(str(CASES / "*.json"))):
        d = json.loads(Path(f).read_text("utf-8"))
        if "by_model" not in d:
            continue
        ds, qw = d["by_model"]["deepseek"], d["by_model"]["dashscope"]
        oa = d["official_answer"]
        if not d.get("needs_arbiter"):
            # consensus: pick the must-not-mint-clean candidate (prefer DeepSeek, the prod lane)
            chosen = ds if ds.get("must_not_mint_ok") else qw
            consensus.append({"case_file": d["case_file"], "question_id": d["question_id"],
                              "point_type": chosen.get("point_type"), "segments": chosen.get("segments"),
                              "list_rule": chosen.get("list_rule"), "penalty_rule": chosen.get("penalty_rule"),
                              "resolution": "consensus"})
            continue
        r = d.get("arbiter_reason", {})
        type_agree = not r.get("type_disagree")
        mint_ok_both = ds.get("must_not_mint_ok") and qw.get("must_not_mint_ok")
        if type_agree and mint_ok_both and r.get("count_disagree"):
            # deterministic tie-break by type-conditioned granularity
            ptype = ds.get("point_type") or qw.get("point_type")
            if ptype in _FINE:
                pick = ds if ds.get("n_segments", 0) >= qw.get("n_segments", 0) else qw
            elif ptype in _COARSE:
                pick = ds if ds.get("n_segments", 0) <= qw.get("n_segments", 0) else qw
            else:  # mixed with type-agreement but count split → still needs judgment → Opus
                pick = None
            if pick is not None and _mnm_ok(pick.get("segments") or [], oa):
                deterministic.append({"case_file": d["case_file"], "question_id": d["question_id"],
                                      "point_type": ptype, "segments": pick.get("segments"),
                                      "list_rule": pick.get("list_rule"), "penalty_rule": pick.get("penalty_rule"),
                                      "resolution": f"deterministic_tiebreak_{ptype}"})
                continue
        # everything else → Opus
        opus.append({"case_file": d["case_file"], "question_id": d["question_id"],
                     "official_answer": oa,
                     "candidate_A_deepseek": {"point_type": ds.get("point_type"), "segments": ds.get("segments"),
                                              "list_rule": ds.get("list_rule"), "penalty_rule": ds.get("penalty_rule"),
                                              "must_not_mint_ok": ds.get("must_not_mint_ok")},
                     "candidate_B_qwen": {"point_type": qw.get("point_type"), "segments": qw.get("segments"),
                                          "list_rule": qw.get("list_rule"), "penalty_rule": qw.get("penalty_rule"),
                                          "must_not_mint_ok": qw.get("must_not_mint_ok")}})

    # write consensus + deterministic resolved sets
    (OUT / "resolved_consensus.json").write_text(json.dumps(consensus, ensure_ascii=False, indent=1), "utf-8")
    (OUT / "resolved_deterministic.json").write_text(json.dumps(deterministic, ensure_ascii=False, indent=1), "utf-8")

    # batch opus cohort ~11/batch
    per = 11
    batches = [opus[i:i + per] for i in range(0, len(opus), per)]
    for i, b in enumerate(batches):
        (BATCHES / f"batch_{i:02d}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), "utf-8")

    summary = {
        "total_cases": len(consensus) + len(deterministic) + len(opus),
        "consensus_no_arbiter": len(consensus),
        "deterministic_tiebreak": len(deterministic),
        "opus_cohort": len(opus),
        "opus_batches": len(batches),
        "cost_note": f"Opus runs on {len(opus)} cases in {len(batches)} batches; "
                     f"{len(deterministic)} resolved free by type-rule tie-break.",
    }
    (OUT / "stage2_prep_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
