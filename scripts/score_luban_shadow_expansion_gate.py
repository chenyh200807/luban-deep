#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_luban_agentic_grading_harness import score_agentic_predictions
from scripts.score_luban_human_validation_slice import score_human_labels


DEFAULT_OUTPUT_DIR = Path("artifacts/luban_agentic_grading_harness/shadow_expansion_gate_20260603")

GATE = {
    "min_sample_count": 50,
    "max_sample_count": 100,
    "min_point_hit_agreement": 0.93,
    "max_mean_abs_score_delta": 0.55,
    "max_unsupported_judgment_count": 0,
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _labels_path(slice_spec: dict[str, str]) -> Path:
    filled = slice_spec.get("labels_filled")
    if filled and Path(filled).exists():
        return Path(filled)
    return Path(slice_spec["labels"])


def _slice_validation(slice_spec: dict[str, str]) -> dict[str, Any]:
    labels_path = _labels_path(slice_spec)
    scored = score_human_labels(manifest_path=Path(slice_spec["manifest"]), labels_path=labels_path)
    return {
        "name": slice_spec["name"],
        "slice_id": scored.get("slice_id"),
        "label_file": str(labels_path),
        "validation": scored["validation"],
    }


def _aggregate_arm_metrics(per_slice: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = sum(int(row.get("sample_count") or 0) for row in per_slice)
    point_count = sum(int(row.get("point_count") or 0) for row in per_slice)
    unsupported = sum(int(row.get("unsupported_judgment_count") or 0) for row in per_slice)
    disagreement_count = sum(len(row.get("disagreements") or []) for row in per_slice)
    hit_sum = sum(float(row.get("point_hit_agreement") or 0) * int(row.get("point_count") or 0) for row in per_slice)
    delta_sum = sum(float(row.get("mean_abs_score_delta") or 0) * int(row.get("sample_count") or 0) for row in per_slice)
    return {
        "sample_count": sample_count,
        "point_count": point_count,
        "point_hit_agreement": round(hit_sum / point_count, 4) if point_count else 0.0,
        "mean_abs_score_delta": round(delta_sum / sample_count, 4) if sample_count else 0.0,
        "unsupported_judgment_count": unsupported,
        "unsupported_judgment_rate": round(unsupported / point_count, 4) if point_count else 0.0,
        "disagreement_count": disagreement_count,
    }


def _gate_arm(metric: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = []
    samples = int(metric["sample_count"])
    if samples < GATE["min_sample_count"]:
        reasons.append(f"sample_count={samples} < {GATE['min_sample_count']}")
    if samples > GATE["max_sample_count"]:
        reasons.append(f"sample_count={samples} > {GATE['max_sample_count']}")
    if float(metric["point_hit_agreement"]) < GATE["min_point_hit_agreement"]:
        reasons.append(f"point_hit_agreement={metric['point_hit_agreement']} < {GATE['min_point_hit_agreement']}")
    if float(metric["mean_abs_score_delta"]) > GATE["max_mean_abs_score_delta"]:
        reasons.append(f"mean_abs_score_delta={metric['mean_abs_score_delta']} > {GATE['max_mean_abs_score_delta']}")
    if int(metric["unsupported_judgment_count"]) > GATE["max_unsupported_judgment_count"]:
        reasons.append(f"unsupported_judgment_count={metric['unsupported_judgment_count']}")
    return ("pass" if not reasons else "fail", reasons)


def _finding(result: dict[str, Any]) -> str:
    lines = [
        "# FINDING: Luban Shadow Expansion Gate",
        "",
        "> Directional/shadow. This gate requires human labels before any model metric is computed.",
        "",
        f"- status: `{result['status']}`",
        f"- slices: `{len(result.get('slice_validations') or [])}`",
        "",
    ]
    if result["status"] == "blocked_human_labels_incomplete":
        lines.extend(["## Missing Human Labels", ""])
        for item in result["slice_validations"]:
            validation = item["validation"]
            lines.append(
                f"- {item['name']} (`{item.get('label_file')}`): filled `{validation['filled_label_count']}` / "
                f"expected `{validation['expected_label_count']}`, missing `{validation['missing_count']}`, "
                f"invalid `{validation['invalid_count']}`, extra `{validation['extra_count']}`"
            )
        lines.append("")
        lines.append("Do not score model predictions or claim production readiness until labels are complete.")
    else:
        lines.extend(
            [
                "## Arms",
                "",
                "| arm | samples | points | hit_agree | delta | unsupported | gate |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for arm, metric in result.get("arms", {}).items():
            lines.append(
                f"| {arm} | {metric['sample_count']} | {metric['point_count']} | "
                f"{metric['point_hit_agreement']:.4f} | {metric['mean_abs_score_delta']:.4f} | "
                f"{metric['unsupported_judgment_count']} | {metric['gate']} |"
            )
    return "\n".join(lines) + "\n"


def run_expansion_gate(*, slices: list[dict[str, str]], output_dir: Path) -> dict[str, Any]:
    validations = [_slice_validation(slice_spec) for slice_spec in slices]
    incomplete = [
        row
        for row in validations
        if not bool((row.get("validation") or {}).get("is_complete"))
    ]
    if incomplete:
        result = {
            "schema_version": "luban-shadow-expansion-gate.v0.1",
            "status": "blocked_human_labels_incomplete",
            "gate": GATE,
            "slice_validations": validations,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "shadow_expansion_gate.json", result)
        (output_dir / "FINDING_shadow_expansion_gate.md").write_text(_finding(result), encoding="utf-8")
        return result

    scored_slices = []
    arm_rows: dict[str, list[dict[str, Any]]] = {}
    for slice_spec in slices:
        labels_path = _labels_path(slice_spec)
        scored = score_agentic_predictions(
            manifest_path=Path(slice_spec["manifest"]),
            labels_path=labels_path,
            predictions_path=Path(slice_spec["predictions"]),
            review_packet_path=Path(slice_spec["review_packet"]) if slice_spec.get("review_packet") else None,
        )
        scored_slices.append({"name": slice_spec["name"], "label_file": str(labels_path), "score": scored})
        for arm, metric in (scored.get("agentic_arms") or {}).items():
            arm_rows.setdefault(arm, []).append(metric)

    arms = {}
    for arm, rows in arm_rows.items():
        metric = _aggregate_arm_metrics(rows)
        gate, reasons = _gate_arm(metric)
        metric["gate"] = gate
        metric["gate_reasons"] = reasons
        arms[arm] = metric

    result = {
        "schema_version": "luban-shadow-expansion-gate.v0.1",
        "status": "pass" if any(row["gate"] == "pass" for row in arms.values()) else "fail",
        "gate": GATE,
        "slice_validations": validations,
        "slices": scored_slices,
        "arms": arms,
        "production_runtime_decision": "not_approved",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "shadow_expansion_gate.json", result)
    (output_dir / "FINDING_shadow_expansion_gate.md").write_text(_finding(result), encoding="utf-8")
    return result


def _load_slices(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return list(payload.get("slices") or [])
    if isinstance(payload, list):
        return payload
    raise TypeError("slice config must be a list or an object with a slices list")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Luban 50-100 answer shadow expansion gate.")
    parser.add_argument("--slices-config", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    result = run_expansion_gate(slices=_load_slices(Path(args.slices_config)), output_dir=Path(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "blocked_human_labels_incomplete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
