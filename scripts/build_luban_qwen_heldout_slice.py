#!/usr/bin/env python3
"""Build a HELD-OUT validation slice for the qwen3.7-plus expansion round.

The dev slice (po_slice_20260601) used 12 cases. This builds a clean held-out slice
from the golden cases that NEVER appeared in the dev slice, reusing the existing
LLM-simulated diverse student answers. Output schema matches the agentic grading
harness so the existing qwen runner + scorer work unchanged.

directional/shadow. Emits a BLIND packet + a blank human-label template + a manifest.
Does NOT fabricate human labels — the PO fills po_labels_template.csv; that is the gate.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEV_MANIFEST = PROJECT_ROOT / "artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json"
DEFAULT_OUT = PROJECT_ROOT / "artifacts/luban_human_validation_v1/po_slice_20260603_heldout"

RESPONSE_SCHEMA = {
    "prediction_sets_required_fields": ["arm", "predictions"],
    "per_point_required_fields": [
        "case_id", "student_id", "point_id", "hit", "score",
        "confidence", "evidence_span", "rationale", "unsupported",
    ],
    "allowed_hit_values": ["hit", "miss", "partial"],
}
AGENTIC_RULE = (
    "LLM handles student-answer evidence extraction and point-level adjudication; "
    "deterministic code validates schema, computes totals, and scores against human labels."
)


def _ledger_rows(sample: dict, points: list[dict]) -> list[dict]:
    max_by = {str(p["point_id"]): float(p.get("max_score") or 0) for p in points}
    hits = {}
    ledger = sample.get("ground_truth_ledger") or {}
    for row in ledger.get("point_hits") or []:
        hits[str(row.get("point_id"))] = str(row.get("hit") or "")
    rows = []
    for p in points:
        pid = str(p["point_id"])
        mx = max_by.get(pid, 0.0)
        hit = hits.get(pid, "")
        gold = mx if hit == "hit" else (mx / 2 if hit == "partial" else 0.0)
        rows.append({"point_id": pid, "ledger_hit": hit, "max_score": mx, "gold_score": gold})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=5, help="diverse students per held-out case")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    dev = json.loads(DEV_MANIFEST.read_text(encoding="utf-8"))
    dev_cases = {str(s["case_id"]) for s in dev.get("selected_samples") or []}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tasks: list[dict] = []
    selected_samples: list[dict] = []
    label_rows: list[list] = []
    heldout_cases: list[str] = []

    for case in golden["cases"]:
        cid = str(case["case_id"])
        if cid in dev_cases:
            continue  # held-out = never in dev slice
        heldout_cases.append(cid)
        points = case.get("gold_scoring_points") or []
        sp = [
            {
                "point_id": p["point_id"], "label": p.get("label"), "max_score": p.get("max_score"),
                "official_basis": p.get("official_basis"), "list_rule": p.get("list_rule"),
                "penalty_rule": p.get("penalty_rule"),
            }
            for p in points
        ]
        samples = (case.get("eval_samples") or [])[: args.students]
        for s in samples:
            sid = str(s["student_id"])
            tasks.append(
                {
                    "case_id": cid, "question_node": case.get("question_node"), "stem": case.get("stem"),
                    "official_answer": case.get("official_answer"), "official_analysis": case.get("official_analysis"),
                    "penalty_rule": case.get("penalty_rule"),
                    "scoring_points": sp, "task_id": f"{cid}::{sid}", "student_id": sid,
                    "student_archetype": s.get("archetype"), "student_answer": s.get("answer_text"),
                }
            )
            selected_samples.append(
                {"case_id": cid, "student_id": sid, "archetype": s.get("archetype"), "ledger_point_rows": _ledger_rows(s, points)}
            )
            for p in points:
                label_rows.append([cid, sid, p["point_id"], p.get("max_score"), p.get("label"), "", "", "", ""])

    slice_id = f"luban-qwen-heldout-{len(heldout_cases)}cases-{len(tasks)}samples"
    packet = {
        "slice_id": slice_id, "status": "blind_awaiting_human_labels",
        "purpose": "Held-out generalization check for qwen3.7-plus no-think production-config single-model grader.",
        "grading_guideline": "踩字：采分点术语必须来自教材/规范原文，近义/大白话不给分。",
        "agentic_rule": AGENTIC_RULE, "response_schema": RESPONSE_SCHEMA, "tasks": tasks,
    }
    (out / "agentic_grading_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {"slice_id": slice_id, "status": "blind_awaiting_human_labels", "selected_samples": selected_samples}
    (out / "internal_slice_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with (out / "po_labels_template.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "student_id", "point_id", "max_score", "point_label", "human_hit", "human_score", "human_error_codes", "human_note"])
        w.writerows(label_rows)

    finding = "\n".join(
        [
            "# FINDING: Qwen3.7-plus Held-out Validation Slice",
            "",
            "> Directional/shadow. This only prepares a blind human-label package; it does not fabricate labels.",
            "",
            "## Scope",
            "",
            f"- heldout_cases: `{len(heldout_cases)}`",
            f"- samples: `{len(tasks)}`",
            f"- point_label_rows: `{len(label_rows)}`",
            "- model_candidate: `qwen3.7-plus no-think production-config primary`",
            "- runtime_status: `not_approved`",
            "",
            "## Files",
            "",
            "- `agentic_grading_packet.json`: blind packet for model grading.",
            "- `internal_slice_manifest.json`: internal ledger reference; do not show to graders.",
            "- `po_labels_template.csv`: blank human-label template; PO/teacher must fill before scoring.",
            "",
            "## Next Gate",
            "",
            "Combine this 40-answer held-out slice with the existing 24-answer human slice after human labels are filled. "
            "That gives 64 answers, satisfying the 50-100 answer shadow gate scope before any runtime proposal.",
        ]
    )
    (out / "FINDING_qwen_heldout_slice.md").write_text(finding + "\n", encoding="utf-8")

    print(f"held-out cases ({len(heldout_cases)}): {heldout_cases}")
    print(f"tasks(samples)={len(tasks)}  point-label rows={len(label_rows)}")
    print(f"out -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
