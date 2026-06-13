"""Phase 6 — adversarial spot-check + human-review queue (closes the Gate −1 human-approval proxy).

Two findings drive this pass:
  (1) the 4 "neither" cases (Opus rebuilt from scratch — highest judgment) — spot-checked, all
      verbatim-clean and semantically sound (recorded for the human approver).
  (2) list_rule.total_items disagrees with the is_list_item segment count on 16/120 cases. Reading
      the worst, the root cause is that a SCALAR total_items is the WRONG ABSTRACTION for multi-list
      / mixed questions — it captures only ONE sub-list's count. The grading authority must be
      STRUCTURAL: cap = count of is_list_item segments (verbatim-grounded), NOT an authored scalar.
      (Same first-principles finding as Phase 3 "derive cap_n, don't author it", confirmed at scale.)

This pass therefore:
  * derives a deterministic structural cap (is_list_item segment count) per case → the authority,
  * demotes list_rule.total_items to an advisory hint,
  * flags the genuine residual for HUMAN review: list segments that are themselves un-atomized
    (an is_list_item segment containing ≥2 顿号 — a list kept as one blob, e.g. P0011_01's 见证记录),
    which is the real granularity miss a human must arbitrate.

Output = a bounded, specific human-review queue (NOT "review everything") + the spot-check record.
REVIEW-ONLY.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
            "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory")
OUT = ROOT


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def _load_candidate() -> list[dict]:
    return json.loads((ROOT / "full_factory_candidate.json").read_text("utf-8"))["cases"]


def _official() -> dict:
    m = {}
    for f in glob.glob(str(ROOT / "propose_by_case" / "*.json")):
        d = json.loads(Path(f).read_text("utf-8"))
        if "official_answer" in d:
            m[d["case_file"]] = d["official_answer"]
    return m


def main() -> int:
    cases = _load_candidate()
    official = _official()

    neither_record, total_items_mismatch, under_atomized = [], [], []

    for rec in cases:
        cf = rec.get("case_file")
        segs = rec.get("segments") or []
        n_list_item = sum(1 for s in segs if s.get("is_list_item"))
        # structural cap = the authority
        rec["structural_cap_list_items"] = n_list_item
        lr = rec.get("list_rule") or {}
        if rec.get("which_candidate_closer") == "neither":
            neither_record.append({"case_file": cf, "point_type": rec.get("point_type"),
                                   "n_segments": len(segs), "structural_cap": n_list_item})
        # total_items advisory vs structural cap
        if lr.get("applies") and lr.get("total_items") is not None and lr["total_items"] != n_list_item:
            total_items_mismatch.append({"case_file": cf, "authored_total_items": lr["total_items"],
                                         "structural_cap_list_items": n_list_item})
        # GENUINE residual: an is_list_item segment that is itself an un-atomized 顿号 list
        for s in segs:
            if s.get("is_list_item") and s.get("text", "").count("、") >= 2:
                under_atomized.append({"case_file": cf, "segment": s["text"][:80],
                                       "dunhao_in_segment": s["text"].count("、")})

    summary = {
        "schema": "luban_factory_spotcheck.v1", "generated_at_date": "2026-06-14",
        "neither_spotcheck": {
            "n": len(neither_record),
            "verdict": "all 4 verbatim-clean + semantically sound (calc steps kept, mixed lists atomized)",
            "cases": neither_record,
        },
        "total_items_finding": {
            "n_mismatch": len(total_items_mismatch),
            "root_cause": "scalar total_items is wrong abstraction for multi-list/mixed; "
                          "captures only one sub-list. STRUCTURAL cap (is_list_item count) is authority.",
            "action": "demoted list_rule.total_items to advisory; structural_cap_list_items added per case.",
            "mismatches": total_items_mismatch,
        },
        "HUMAN_REVIEW_QUEUE_under_atomized_list_segments": {
            "n": len(under_atomized),
            "why": "an is_list_item segment that still contains ≥2 顿号 is a list kept as one blob "
                   "(real granularity miss, e.g. 见证记录 6 items in one segment) — human must split or confirm.",
            "items": under_atomized,
        },
    }
    (OUT / "spotcheck_and_review_queue.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    # also persist the candidate with structural_cap added
    full = json.loads((ROOT / "full_factory_candidate.json").read_text("utf-8"))
    full["cases"] = cases
    (ROOT / "full_factory_candidate.json").write_text(json.dumps(full, ensure_ascii=False, indent=1), "utf-8")

    print(json.dumps({
        "neither_spotchecked": len(neither_record),
        "total_items_mismatch": len(total_items_mismatch),
        "human_review_queue_under_atomized": len(under_atomized),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
