#!/usr/bin/env python3
"""Build the policy-queue case package from the 12 unresolved consensus_gold_v1 frontier points.

Pure offline organizer: joins the unresolved queue with the frontier adjudication packet
(stem/official_answer/student_answer/scoring_point/model_judgments) and the candidate
shadow-run disagreements. Assigns a deterministic conflict_axis + suspected_policy_gap.

directional/shadow. Reads NO human labels, NO ledger-as-truth, NO RAG, calls NO model.
The 12 unresolved are NOT added to consensus_gold_v1; this only produces policy assets.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

_RANK = {"miss": 0, "partial": 1, "hit": 2}


def _conflict_axis(policy_type: str, votes: dict, dissent_reason: str) -> tuple[str, str]:
    hits = [v[0] for v in votes.values()]
    ranks = sorted(_RANK[h] for h in hits)
    spread = ranks[-1] - ranks[0] if ranks else 0
    qwen = votes.get("qwen37", (None, None))[0]
    if policy_type == "calculation":
        return "calculation_process_score", "计算过程/取整口径未定"
    if policy_type == "list_rule":
        # qwen counts fewer items than the majority -> denominator/rounding boundary
        if qwen in ("partial", "miss"):
            return "list_rule_denominator", "list_rule 命中项数(分母 k/n)口径模型不一致;qwen 计数更严"
        return "list_rule_denominator", "list_rule 命中项数口径不一致"
    # exact_required
    if spread >= 2:  # miss..hit full spread -> some saw the core term, others did not
        return "exact_required_near_synonym", "学生写核心词但缺修饰语/或近义,是否算命中口径不一致"
    return "strict_vs_lenient", "exact_required 严松派对同一 span 判定不一致"


def build_policy_queue(*, unresolved_csv: Path, packet_path: Path, qwen_disagree_csv: Path | None, deepseek_disagree_csv: Path | None) -> list[dict]:
    packet = {(t["case_id"], t["student_id"], t["point_id"]): t for t in json.loads(packet_path.read_text(encoding="utf-8"))["tasks"]}

    def _disagree_map(path: Path | None) -> dict:
        if not path or not path.exists():
            return {}
        out = {}
        for r in csv.DictReader(path.open(encoding="utf-8")):
            out[(r.get("case_id"), r.get("student_id"), r.get("point_id"))] = r
        return out

    qd = _disagree_map(qwen_disagree_csv)
    dd = _disagree_map(deepseek_disagree_csv)

    cases = []
    for r in csv.DictReader(unresolved_csv.open(encoding="utf-8")):
        key = (r["case_id"], r["student_id"], r["point_id"])
        t = packet.get(key)
        if t is None:
            raise SystemExit(f"STOP: unresolved point {key} not found in frontier packet — queue/packet mismatch")
        mj = t.get("model_judgments") or {}
        votes = {a: (v.get("hit"), v.get("score")) for a, v in mj.items() if isinstance(v, dict)}
        axis, gap = _conflict_axis(r["policy_type"], votes, r.get("dissent_reason", ""))
        sp = t.get("scoring_point") or {}
        cases.append(
            {
                "case_id": r["case_id"], "student_id": r["student_id"], "point_id": r["point_id"],
                "policy_type": r["policy_type"], "dissent_reason": r.get("dissent_reason"),
                "stem": (t.get("stem") or "")[:600],
                "official_answer": t.get("official_answer"),
                "student_answer": t.get("student_answer"),
                "scoring_point": sp.get("label") if isinstance(sp, dict) else sp,
                "model_judgments": {a: {"hit": v[0], "score": v[1]} for a, v in votes.items()},
                "qwen_prediction": qd.get(key) or ({"hit": votes["qwen37"][0], "score": votes["qwen37"][1]} if "qwen37" in votes else None),
                "deepseek_prediction": dd.get(key) or ({"hit": votes["deepseek"][0], "score": votes["deepseek"][1]} if "deepseek" in votes else None),
                "conflict_axis": axis,
                "suspected_policy_gap": gap,
            }
        )
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    base = Path("artifacts/luban_consensus_gold")
    ap.add_argument("--unresolved", default=str(base / "po_slice_20260603_heldout_v1/frontier_unresolved_queue.csv"))
    ap.add_argument("--packet", default=str(base / "po_slice_20260603_heldout/frontier_adjudication/frontier_adjudication_packet.json"))
    ap.add_argument("--qwen-disagree", default=str(base / "shadow_runs/qwen37_nothink_heldout_v1_20260603/consensus_gold_shadow_disagreements.csv"))
    ap.add_argument("--deepseek-disagree", default=str(base / "shadow_runs/deepseek_v4_heldout_v1_20260603/consensus_gold_shadow_disagreements.csv"))
    ap.add_argument("--out-dir", default=str(base / "policy_queue_20260603"))
    args = ap.parse_args()

    cases = build_policy_queue(
        unresolved_csv=Path(args.unresolved), packet_path=Path(args.packet),
        qwen_disagree_csv=Path(args.qwen_disagree), deepseek_disagree_csv=Path(args.deepseek_disagree),
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "policy_queue_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "policy_queue_cases.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "student_id", "point_id", "policy_type", "conflict_axis", "suspected_policy_gap"])
        for c in cases:
            w.writerow([c["case_id"], c["student_id"], c["point_id"], c["policy_type"], c["conflict_axis"], c["suspected_policy_gap"]])

    from collections import Counter

    print("policy_queue cases:", len(cases))
    print("conflict_axis:", dict(Counter(c["conflict_axis"] for c in cases)))
    print("by case:", dict(Counter(c["case_id"] for c in cases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
