"""Phase 8 — assemble the multi-AI team's verdict on the 51-segment queue + apply to candidate.

Closes the loop started in Phase 6. The 51 顿号-heuristic flags were an UPPER BOUND; the team
(DeepSeek+Qwen propose → Codex adversarial refute → Opus anchor-verify+final) converged them:

  * 33 atomize  — genuinely independent 踩字 items → split into verbatim sub-items
  * 15 keep     — joint sub-conditions of one point (load combos, description dims, examples)
  * 3 not_a_list — mis-flagged prose

Honest result: only 33/51 (65%) truly needed atomizing; 18/51 (35%) were heuristic over-flags —
exactly the "load-symbol 顿号 over-flag" Phase 6 called out. Adversarial Codex caught 5 cheap-model
consensus errors, all upheld by Opus. Every applied split is must-not-mint re-verified here.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

FAC = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
           "/artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory")
S3 = FAC / "stage3_atomization"


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def main() -> int:
    stageA = json.loads((S3 / "stageA_propose.json").read_text("utf-8"))["results"]
    codex_b_ids = {x["id"] for x in json.loads((S3 / "stageB_codex_verdict.json").read_text("utf-8"))}
    codex_input = {x["id"]: x["segment"] for x in json.loads((S3 / "stageB_codex_input.json").read_text("utf-8"))}
    codex_b_segments = {codex_input[i] for i in codex_b_ids}
    opus = json.loads((S3 / "stageC_opus_verdict.json").read_text("utf-8"))
    opus_by_seg = {o["segment"]: o for o in opus}

    dispositions = []  # final per-segment
    for r in stageA:
        seg = r["segment"]
        cv = r["consensus_verdict"]
        if r["contested"] or seg in codex_b_segments:
            o = opus_by_seg.get(seg)
            if not o:
                dispositions.append({"case_file": r["case_file"], "segment": seg,
                                     "final": "UNRESOLVED", "items": [], "source": "missing_opus"})
                continue
            dispositions.append({"case_file": r["case_file"], "segment": seg,
                                 "final": o["final_verdict"], "items": o.get("items") or [],
                                 "source": "opus_final", "reason": o.get("reason", "")[:90]})
        else:
            # uncontested + not Codex-refuted → trust consensus
            items = r["by_model"]["deepseek"]["items"] if cv == "A_atomize" else []
            dispositions.append({"case_file": r["case_file"], "segment": seg,
                                 "final": cv, "items": items, "source": "cross_family_consensus"})

    # normalize verdict labels (A_atomize / B_keep / C_not_a_list)
    def norm(v: str) -> str:
        return {"A_atomize": "atomize", "B_keep": "keep", "C_not_a_list": "not_a_list"}.get(v, v)

    # must-not-mint re-verify every atomize split
    mint_violations = []
    for d in dispositions:
        d["final"] = norm(d["final"])
        if d["final"] == "atomize":
            seg_h = _hanzi(d["segment"])
            bad = [x[:24] for x in d["items"] if _hanzi(x) and _hanzi(x) not in seg_h]
            d["mnm_ok"] = not bad
            if bad:
                mint_violations.append({"case_file": d["case_file"], "minted": bad})

    n = len(dispositions)
    by_final = {}
    for d in dispositions:
        by_final[d["final"]] = by_final.get(d["final"], 0) + 1
    atomize = [d for d in dispositions if d["final"] == "atomize"]
    extra_points = sum(len(d["items"]) - 1 for d in atomize if d["items"])  # net new scoring points

    summary = {
        "schema": "luban_atomization_team_closure.v1", "generated_at_date": "2026-06-14",
        "team": "DeepSeek+Qwen propose → Codex adversarial refute → Opus anchor-verify+final",
        "n_queue": n,
        "final_disposition": by_final,
        "heuristic_over_flag_finding": {
            "flagged": 51, "truly_atomize": by_final.get("atomize", 0),
            "kept_or_prose": by_final.get("keep", 0) + by_final.get("not_a_list", 0),
            "over_flag_rate": round((by_final.get("keep", 0) + by_final.get("not_a_list", 0)) / n, 3),
            "note": "顿号 heuristic over-flagged ~35%: load combos / description dims / parenthetical examples / prose.",
        },
        "adversarial_value": {
            "codex_refuted_cheap_consensus": len(codex_b_ids),
            "opus_upheld_codex": sum(1 for o in opus if o.get("codex_refutation_upheld") is True),
            "opus_ruled_contested": sum(1 for o in opus if o.get("codex_refutation_upheld") in (None,)),
        },
        "must_not_mint_violations": mint_violations,
        "net_new_scoring_points_from_atomize": extra_points,
    }
    (S3 / "atomization_closure.json").write_text(
        json.dumps({"summary": summary, "dispositions": dispositions}, ensure_ascii=False, indent=1), "utf-8")

    # APPLY the 33 atomize splits back into the candidate (keep/not_a_list unchanged)
    atom_by_seg = {d["segment"]: d["items"] for d in dispositions
                   if d["final"] == "atomize" and d.get("mnm_ok") and d["items"]}
    full = json.loads((FAC / "full_factory_candidate.json").read_text("utf-8"))
    applied = 0
    for rec in full["cases"]:
        new_segs = []
        for s in rec.get("segments") or []:
            items = atom_by_seg.get(s.get("text"))
            if s.get("is_list_item") and items:
                applied += 1
                for it in items:
                    new_segs.append({"text": it, "is_list_item": True,
                                     "exact_term_required": s.get("exact_term_required", True)})
            else:
                new_segs.append(s)
        rec["segments"] = new_segs
    # recompute point count + final must-not-mint over the applied candidate
    official = {}
    for f in glob.glob(str(FAC / "propose_by_case" / "*.json")):
        d = json.loads(Path(f).read_text("utf-8"))
        official[d["case_file"]] = d.get("official_answer", "")
    total_pts, mnm_clean = 0, 0
    for rec in full["cases"]:
        segs = rec.get("segments") or []
        total_pts += len(segs)
        oa_h = _hanzi(official.get(rec["case_file"], ""))
        if all(_hanzi(s.get("text", "")) in oa_h for s in segs if _hanzi(s.get("text", ""))):
            mnm_clean += 1
    full["summary"]["post_atomization"] = {
        "segments_atomized": applied, "total_scoring_points": total_pts,
        "mean_points_per_q": round(total_pts / len(full["cases"]), 2),
        "final_must_not_mint_clean": f"{mnm_clean}/{len(full['cases'])}",
    }
    (FAC / "full_factory_candidate.json").write_text(json.dumps(full, ensure_ascii=False, indent=1), "utf-8")
    summary["applied_to_candidate"] = full["summary"]["post_atomization"]
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
