#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_GOLD = Path("artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/consensus_gold_v1.json")
DEFAULT_SUMMARY = Path("artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/consensus_gold_v1_summary.json")
DEFAULT_ADJUDICATED = Path("artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/frontier_adjudicated_gold.json")
DEFAULT_UNRESOLVED = Path("artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/frontier_unresolved_queue.csv")
DEFAULT_MANIFEST = Path("artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/consensus_gold_v1_manifest.json")
DEFAULT_GOLDEN = Path("deeptutor/services/benchmark/fixtures/luban_case_grading_golden_no_human_v1_5.json")

ALLOWED_HITS = {"hit", "partial", "miss"}
QWEN_GATE = {
    "min_hit_agreement": 0.92,
    "max_mean_abs_score_delta": 0.10,
    "max_unsupported_positive": 0,
    "max_exact_required_major_violation": 0,
    "max_penalty_rule_major_violation": 0,
    "max_missing_predictions": 0,
}
DEEPSEEK_GATE = {
    "min_hit_agreement": 0.92,
    "max_unsupported_positive": 0,
    "max_missing_predictions": 0,
}
FORBIDDEN_USES = [
    "production runtime grading",
    "human gold claim",
    "pr_gate_core hard block",
    "RAG authority",
    "CaseGradingSkillKernel replacement",
]
ALLOWED_USES = [
    "offline gold production",
    "shadow regression",
    "model bakeoff",
    "distillation examples",
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_entry(path: Path) -> dict[str, Any]:
    return {"sha256": _sha256(path), "bytes": path.stat().st_size}


def _read_unresolved_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def build_gold_manifest(
    *,
    gold_path: Path = DEFAULT_GOLD,
    summary_path: Path = DEFAULT_SUMMARY,
    adjudicated_path: Path = DEFAULT_ADJUDICATED,
    unresolved_path: Path = DEFAULT_UNRESOLVED,
    output_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    gold = _read_json(gold_path)
    summary = _read_json(summary_path)
    inputs = [gold_path, summary_path, adjudicated_path, unresolved_path]
    manifest = {
        "schema_version": "luban-consensus-gold-manifest.v0.1",
        "gold_id": "luban-heldout-consensus-gold-v1-20260603",
        "created_at": datetime.now(UTC).isoformat(),
        "source_slice": "po_slice_20260603_heldout",
        "total_points": int(summary.get("original_total_points") or len(gold)),
        "gold_points": len(gold),
        "coverage": float(summary.get("auto_gold_coverage") or 0),
        "unresolved_points": int(summary.get("frontier_unresolved") or _read_unresolved_count(unresolved_path)),
        "input_files": [str(path) for path in inputs],
        "input_hashes": {str(path): _hash_entry(path) for path in inputs if path.exists()},
        "builder_scripts": [
            "scripts/build_luban_consensus_gold.py",
            "scripts/build_luban_multimodel_jury_gold.py",
            "scripts/build_luban_frontier_adjudicated_gold.py",
        ],
        "model_arms": ["gpt55", "opus48", "deepseek_v4", "qwen37"],
        "span_guard_status": "applied; unsupported-positive must be 0 for shadow gate pass",
        "resolution_class_counts": dict(summary.get("frontier_resolution_classes") or {}),
        "limitations": [
            "directional/shadow only",
            "not human gold",
            "held-out v1 has 12 unresolved policy-review points excluded from denominator",
            "leave-one-out scoring is model-jury agreement, not production accuracy",
        ],
        "allowed_uses": ALLOWED_USES,
        "forbidden_uses": FORBIDDEN_USES,
    }
    _write_json(output_path, manifest)
    return manifest


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id"))


def _normal_hit(value: Any) -> str:
    hit = str(value or "").strip()
    return hit if hit in ALLOWED_HITS else "miss"


def _load_predictions(path: Path, arm: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = _read_json(path)
    for prediction_set in payload.get("prediction_sets") or []:
        if str(prediction_set.get("arm")) == arm:
            return {_key(row): row for row in prediction_set.get("predictions") or []}
    raise ValueError(f"arm {arm!r} not found in {path}")


def _policy_index(golden_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not golden_path.exists():
        return {}
    golden = _read_json(golden_path)
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for case in golden.get("cases") or []:
        case_id = str(case.get("case_id"))
        for point in case.get("gold_scoring_points") or []:
            point_id = str(point.get("point_id"))
            point_type = str(point.get("point_type") or "")
            if point_type == "calculation":
                policy_type = "calculation"
            elif point_type == "figure_label":
                policy_type = "figure_label"
            elif point.get("penalty_rule"):
                policy_type = "penalty_rule"
            elif point.get("list_rule"):
                policy_type = "list_rule"
            else:
                policy_type = "exact_required"
            index[(case_id, point_id)] = {"policy_type": policy_type, "max_score": float(point.get("max_score") or 0)}
    return index


def _avg(values: list[float]) -> float:
    return round(float(mean(values)), 4) if values else 0.0


def _gate_for_arm(arm: str) -> dict[str, float]:
    lowered = arm.lower()
    if "deepseek" in lowered:
        return DEEPSEEK_GATE
    return QWEN_GATE


def _passes(metrics: dict[str, Any], gate: dict[str, float]) -> bool:
    if metrics["point_hit_agreement"] < gate["min_hit_agreement"]:
        return False
    if metrics["missing_predictions"] > gate["max_missing_predictions"]:
        return False
    if metrics["unsupported_positive"] > gate["max_unsupported_positive"]:
        return False
    if "max_mean_abs_score_delta" in gate and metrics["mean_abs_score_delta"] > gate["max_mean_abs_score_delta"]:
        return False
    if metrics.get("exact_required_major_violation", 0) > gate.get("max_exact_required_major_violation", 999999):
        return False
    if metrics.get("penalty_rule_major_violation", 0) > gate.get("max_penalty_rule_major_violation", 999999):
        return False
    return True


def _report(metrics: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# FINDING: Luban Consensus Gold Shadow Gate",
            "",
            "> Directional/shadow only. This is not production runtime approval and is not a human-gold claim.",
            "",
            "## Summary",
            "",
            f"- arm: `{metrics['arm']}`",
            f"- pass: `{metrics['pass']}`",
            f"- evaluated points: `{metrics['evaluated_points']}`",
            f"- missing predictions: `{metrics['missing_predictions']}`",
            f"- point hit agreement: `{metrics['point_hit_agreement']:.4f}`",
            f"- mean abs score delta: `{metrics['mean_abs_score_delta']:.4f}`",
            f"- unsupported-positive: `{metrics['unsupported_positive']}`",
            f"- disagreements: `{metrics['disagreement_count']}`",
            "",
            "## Boundary",
            "",
            "- Does not enter `pr_gate_core`.",
            "- Does not enter production grading runtime.",
            "- Does not replace `CaseGradingSkillKernel`.",
            "- The 12 unresolved policy-review points are excluded from the gold denominator.",
            "",
        ]
    )


def run_shadow_gate(
    *,
    gold_path: Path,
    manifest_path: Path,
    predictions_path: Path,
    arm: str,
    golden_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    gold_rows = list(_read_json(gold_path))
    manifest = _read_json(manifest_path)
    predictions = _load_predictions(predictions_path, arm)
    policy = _policy_index(golden_path)

    hit_matches: list[float] = []
    score_deltas: list[float] = []
    missing: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    unsupported_positive = 0
    policy_disagreements: Counter[str] = Counter()
    exact_required_major_violation = 0
    penalty_rule_major_violation = 0

    for gold in gold_rows:
        key = _key(gold)
        pred = predictions.get(key)
        case_id, _, point_id = key
        policy_type = policy.get((case_id, point_id), {}).get("policy_type", "unknown")
        if pred is None:
            missing.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "policy_type": policy_type})
            hit_matches.append(0.0)
            score_deltas.append(abs(float(gold.get("gold_score") or 0)))
            policy_disagreements[policy_type] += 1
            continue

        pred_hit = _normal_hit(pred.get("hit"))
        pred_score = float(pred.get("score") or 0)
        gold_hit = _normal_hit(gold.get("gold_hit"))
        gold_score = float(gold.get("gold_score") or 0)
        is_positive = pred_hit in {"hit", "partial"} or pred_score > 0
        if is_positive and (bool(pred.get("unsupported")) or not str(pred.get("evidence_span") or "").strip()):
            unsupported_positive += 1

        hit_match = pred_hit == gold_hit
        score_delta = abs(pred_score - gold_score)
        hit_matches.append(1.0 if hit_match else 0.0)
        score_deltas.append(score_delta)
        if not hit_match or score_delta > 1e-6:
            policy_disagreements[policy_type] += 1
            if policy_type == "exact_required" and pred_score > gold_score:
                exact_required_major_violation += 1
            if policy_type == "penalty_rule" and pred_score > gold_score:
                penalty_rule_major_violation += 1
            disagreements.append(
                {
                    "case_id": key[0],
                    "student_id": key[1],
                    "point_id": key[2],
                    "policy_type": policy_type,
                    "gold_hit": gold_hit,
                    "gold_score": gold_score,
                    "pred_hit": pred_hit,
                    "pred_score": pred_score,
                    "score_delta": round(score_delta, 4),
                    "unsupported": bool(pred.get("unsupported")),
                    "evidence_span": pred.get("evidence_span") or "",
                    "rationale": pred.get("rationale") or "",
                }
            )

    gate = _gate_for_arm(arm)
    metrics = {
        "schema_version": "luban-consensus-gold-shadow.v0.1",
        "status": "directional_shadow",
        "arm": arm,
        "gold_id": manifest.get("gold_id"),
        "gold_points": len(gold_rows),
        "evaluated_points": len(gold_rows),
        "missing_predictions": len(missing),
        "point_hit_agreement": _avg(hit_matches),
        "mean_abs_score_delta": _avg(score_deltas),
        "unsupported_positive": unsupported_positive,
        "disagreement_count": len(disagreements),
        "policy_disagreements": dict(policy_disagreements),
        "exact_required_disagreements": policy_disagreements.get("exact_required", 0),
        "list_rule_disagreements": policy_disagreements.get("list_rule", 0),
        "calculation_disagreements": policy_disagreements.get("calculation", 0),
        "penalty_rule_disagreements": policy_disagreements.get("penalty_rule", 0),
        "figure_label_disagreements": policy_disagreements.get("figure_label", 0),
        "exact_required_major_violation": exact_required_major_violation,
        "penalty_rule_major_violation": penalty_rule_major_violation,
        "gate": gate,
        "pass": False,
        "missing": missing,
    }
    metrics["pass"] = _passes(metrics, gate)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "consensus_gold_shadow_metrics.json", metrics)
    with (output_dir / "consensus_gold_shadow_disagreements.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "case_id",
            "student_id",
            "point_id",
            "policy_type",
            "gold_hit",
            "gold_score",
            "pred_hit",
            "pred_score",
            "score_delta",
            "unsupported",
            "evidence_span",
            "rationale",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(disagreements)
    (output_dir / "consensus_gold_shadow_report.md").write_text(_report(metrics), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Luban consensus-gold v1 shadow regression gate.")
    subparsers = parser.add_subparsers(dest="command")

    manifest_parser = subparsers.add_parser("manifest", help="Freeze consensus_gold_v1 metadata and hashes.")
    manifest_parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    manifest_parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    manifest_parser.add_argument("--adjudicated", type=Path, default=DEFAULT_ADJUDICATED)
    manifest_parser.add_argument("--unresolved", type=Path, default=DEFAULT_UNRESOLVED)
    manifest_parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)

    run_parser = subparsers.add_parser("run", help="Score one prediction arm against frozen consensus_gold_v1.")
    run_parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    run_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run_parser.add_argument("--predictions", type=Path, required=True)
    run_parser.add_argument("--arm", required=True)
    run_parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    run_parser.add_argument("--output-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "manifest":
        result = build_gold_manifest(
            gold_path=args.gold,
            summary_path=args.summary,
            adjudicated_path=args.adjudicated,
            unresolved_path=args.unresolved,
            output_path=args.output,
        )
    elif args.command == "run":
        result = run_shadow_gate(
            gold_path=args.gold,
            manifest_path=args.manifest,
            predictions_path=args.predictions,
            arm=args.arm,
            golden_path=args.golden,
            output_dir=args.output_dir,
        )
    else:
        parser.print_help()
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
