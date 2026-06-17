#!/usr/bin/env python3
"""485 four-model LOO re-validation: asset inventory + missing-prediction map.

Deterministic offline scan. Answers: of the 20题/100答/485 point target, which
(case, student) samples already have (a) a typed-policy packet and (b) per-model
predictions for gpt55 / opus48 / qwen37 / deepseek_v4_flash — and which are missing.

It NEVER treats a missing/data_unavailable cell as ready. directional/shadow.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 100-answer target ledger (case_id, sample_id S1..S5) + per-point gold count
LEDGER = REPO / "artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_184856.json"

# typed-policy packets that already exist
HELDOUT_PACKET = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json"
DEV_PACKET = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_typed_policy_packet.json"

# prediction sources
HELDOUT_PREDS = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_predictions_span_guarded.json"
DEV_PREDS = REPO / "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_predictions_span_guarded.json"

MODELS = ["gpt", "opus", "qwen", "deepseek"]
# map each model to the arm names that count as "has a prediction"
ARM_TO_MODEL = {
    "gpt55_primary": "gpt",
    "opus48_primary": "opus",
    "qwen37_plus_nothink_primary": "qwen",
    "deepseek_v4_flash_typed_policy_primary": "deepseek",
    "deepseek_v4_flash_primary": "deepseek",  # dev arm
}


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _target_samples() -> dict[tuple, int]:
    """(case_id, student_id) -> gold point count, from the 100-answer ledger."""
    d = _read_json(LEDGER)
    out: dict[tuple, int] = {}
    for r in d["rows"]:
        if r["arm"] != "artifact_first":
            continue
        out[(r["case_id"], r["sample_id"])] = len(r.get("gold_point_rows") or [])
    return out


def _packet_samples(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    p = _read_json(path)
    return {(t["case_id"], t["student_id"]) for t in p["tasks"]}


def _pred_samples_by_model(path: Path) -> dict[str, set[tuple]]:
    out: dict[str, set[tuple]] = {m: set() for m in MODELS}
    if not path.exists():
        return out
    p = _read_json(path)
    for s in p.get("prediction_sets", []):
        model = ARM_TO_MODEL.get(s["arm"])
        if not model:
            continue
        for pred in s["predictions"]:
            out[model].add((pred["case_id"], pred["student_id"]))
    return out


def build_inventory() -> dict:
    target = _target_samples()
    typed_policy = _packet_samples(HELDOUT_PACKET) | _packet_samples(DEV_PACKET)

    preds: dict[str, set[tuple]] = {m: set() for m in MODELS}
    for src in (HELDOUT_PREDS, DEV_PREDS):
        for m, samples in _pred_samples_by_model(src).items():
            preds[m] |= samples

    per_sample = []
    missing_rows = []
    for key in sorted(target):
        has_tp = key in typed_policy
        model_has = {m: (key in preds[m]) for m in MODELS}
        row = {"case_id": key[0], "student_id": key[1], "gold_points": target[key],
               "typed_policy_packet": has_tp, **{f"pred_{m}": model_has[m] for m in MODELS}}
        per_sample.append(row)
        missing_models = [m for m in MODELS if not model_has[m]]
        if not has_tp or missing_models:
            missing_rows.append({
                "case_id": key[0], "student_id": key[1],
                "typed_policy_packet_missing": not has_tp,
                "missing_models": ",".join(missing_models),
            })

    n_target = len(target)
    n_tp = sum(1 for r in per_sample if r["typed_policy_packet"])
    four_model_ready = sum(1 for r in per_sample if r["typed_policy_packet"] and all(r[f"pred_{m}"] for m in MODELS))
    summary = {
        "status": "inventory_complete",
        "target_samples": n_target,
        "target_points": sum(target.values()),
        "typed_policy_packet_present_samples": n_tp,
        "typed_policy_packet_missing_samples": n_target - n_tp,
        "four_model_ready_samples": four_model_ready,
        "four_model_missing_samples": n_target - four_model_ready,
        "per_model_prediction_counts": {m: sum(1 for r in per_sample if r[f"pred_{m}"]) for m in MODELS},
        "ready_for_full_485_loo": four_model_ready == n_target,  # only true if EVERYTHING present
    }
    return {"summary": summary, "per_sample": per_sample, "missing": missing_rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(REPO / "artifacts/luban_consensus_gold/deepseek_shadow_v0_485_prep_20260603"))
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    inv = build_inventory()
    (out / "485_asset_inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "485_missing_predictions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "student_id", "typed_policy_packet_missing", "missing_models"])
        w.writeheader()
        w.writerows(inv["missing"])

    s = inv["summary"]
    print(f"target: {s['target_samples']} samples / {s['target_points']} points")
    print(f"typed-policy packet present: {s['typed_policy_packet_present_samples']} / missing: {s['typed_policy_packet_missing_samples']}")
    print(f"four-model ready: {s['four_model_ready_samples']} / missing: {s['four_model_missing_samples']}")
    print(f"per-model preds: {s['per_model_prediction_counts']}")
    print(f"ready_for_full_485_loo: {s['ready_for_full_485_loo']}")
    print(f"missing rows: {len(inv['missing'])} -> {out}/485_missing_predictions.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
