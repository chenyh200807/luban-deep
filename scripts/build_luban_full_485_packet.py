#!/usr/bin/env python3
"""Build the full 485-point typed-policy packet (100 samples / 20 cases).

Joins the golden master corpus (student answers + per-case scoring points) with
the typed_policy classifications already compiled in the held-out + dev packets
(typed_policy is per-case, so it applies to all 5 archetype samples of a case).

Does NOT recreate student answers, does NOT change scoring-point truth, does NOT
use artifact_first/baseline/rag results as gold. directional/shadow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
HELDOUT = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json"
DEV = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_typed_policy_packet.json"


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def build_typed_policy_lookup() -> dict[tuple, dict]:
    """(case_id, point_id) -> typed_policy dict (per-case, first occurrence wins)."""
    tp: dict[tuple, dict] = {}
    for pk in (_read(HELDOUT), _read(DEV)):
        for t in pk["tasks"]:
            for sp in t["scoring_points"]:
                key = (t["case_id"], sp["point_id"])
                if key not in tp and sp.get("typed_policy") is not None:
                    tp[key] = sp["typed_policy"]
    return tp


def build_packet() -> dict:
    golden = _read(GOLDEN)["cases"]
    tp = build_typed_policy_lookup()
    tasks = []
    missing_tp = []
    for c in golden:
        cid = c["case_id"]
        base_points = []
        for gp in c["gold_scoring_points"]:
            key = (cid, gp["point_id"])
            tpol = tp.get(key)
            if tpol is None:
                missing_tp.append(key)
            base_points.append({
                "point_id": gp["point_id"],
                "label": gp.get("label"),
                "max_score": gp.get("max_score"),
                "official_basis": gp.get("official_basis"),
                "list_rule": gp.get("list_rule"),
                "typed_policy": tpol,
            })
        for es in c["eval_samples"]:
            tasks.append({
                "case_id": cid,
                "student_id": es["student_id"],
                "student_archetype": es.get("archetype"),
                "task_id": f"{cid}::{es['student_id']}",
                "stem": c.get("stem"),
                "official_answer": c.get("official_answer"),
                "official_analysis": c.get("official_analysis"),
                "penalty_rule": c.get("penalty_rule"),
                "scoring_points": [dict(p) for p in base_points],
                "student_answer": es.get("answer_text"),
            })
    return {
        "slice_id": "luban-full-485",
        "source": "luban_case_grading_golden_v1 + typed_policy(held-out+dev)",
        "tasks": tasks,
        "_missing_typed_policy": missing_tp,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/unified_typed_policy_packet_485.json"))
    args = ap.parse_args()
    packet = build_packet()
    n_samples = len(packet["tasks"])
    n_points = sum(len(t["scoring_points"]) for t in packet["tasks"])
    missing = packet.pop("_missing_typed_policy")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"samples={n_samples} points={n_points} missing_typed_policy={len(missing)}")
    if missing:
        print("MISSING:", missing[:10])
    assert n_samples == 100, f"expected 100 samples, got {n_samples}"
    assert n_points == 485, f"expected 485 points, got {n_points}"
    assert not missing, "typed_policy missing for some points"
    print(f"OK -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
