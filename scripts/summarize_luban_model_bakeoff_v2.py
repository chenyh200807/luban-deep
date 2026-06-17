#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path(
    "artifacts/luban_agentic_grading_harness/model_bakeoff_v2_20260603"
)

DEFAULT_ARM_SPECS: list[dict[str, str]] = [
    {
        "id": "qwen37_primary",
        "label": "Qwen3.7-plus primary",
        "metrics_path": "artifacts/luban_agentic_grading_harness/po_slice_20260601_crossmodel_qwen_20260603/crossmodel_metrics.json",
        "metrics_key": "agentic_arms.qwen_primary",
        "protocol": "agentic_packet",
    },
    {
        "id": "qwen37_nothink_primary",
        "label": "Qwen3.7-plus no-think primary",
        "metrics_path": "artifacts/luban_agentic_grading_harness/po_slice_20260601_crossmodel_qwen_20260603/qwen_nothink_metrics.json",
        "metrics_key": "agentic_arms.qwen_primary_nothink",
        "protocol": "agentic_packet_nothink",
    },
    {
        "id": "deepseek_typed_policy_span_guarded_dual",
        "label": "DeepSeek-v4-flash typed-policy dual + span guard",
        "metrics_path": "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_prediction_metrics_span_guarded.json",
        "metrics_key": "agentic_arms.deepseek_v4_flash_dual_adjudicated",
        "protocol": "typed_policy_span_guard",
    },
    {
        "id": "gpt55_opus48_dual",
        "label": "GPT5.5 + Opus4.8 dual",
        "metrics_path": "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_prediction_metrics.json",
        "metrics_key": "agentic_arms.dual_adjudicated",
        "protocol": "agentic_packet_dual",
    },
]

GATE = {
    "min_point_hit_agreement": 0.93,
    "max_mean_abs_score_delta": 0.55,
    "max_unsupported_judgment_count": 0,
    "min_sample_count": 24,
    "min_point_count": 131,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path(payload: dict[str, Any], dotted_key: str) -> dict[str, Any]:
    value: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"{dotted_key} not found at {part}")
        value = value[part]
    if not isinstance(value, dict):
        raise TypeError(f"{dotted_key} is not an object")
    return value


def _disagreement_count(metric: dict[str, Any]) -> int:
    disagreements = metric.get("disagreements")
    return len(disagreements) if isinstance(disagreements, list) else int(metric.get("disagreement_count") or 0)


def _gate(metric: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    agreement = float(metric.get("point_hit_agreement") or 0)
    delta = float(metric.get("mean_abs_score_delta") or 0)
    unsupported = int(metric.get("unsupported_judgment_count") or 0)
    sample_count = int(metric.get("sample_count") or 0)
    point_count = int(metric.get("point_count") or 0)
    if agreement < GATE["min_point_hit_agreement"]:
        reasons.append(f"point_hit_agreement={agreement} < {GATE['min_point_hit_agreement']}")
    if delta > GATE["max_mean_abs_score_delta"]:
        reasons.append(f"mean_abs_score_delta={delta} > {GATE['max_mean_abs_score_delta']}")
    if unsupported > GATE["max_unsupported_judgment_count"]:
        reasons.append(f"unsupported_judgment_count={unsupported}")
    if sample_count < GATE["min_sample_count"]:
        reasons.append(f"sample_count={sample_count} < {GATE['min_sample_count']}")
    if point_count < GATE["min_point_count"]:
        reasons.append(f"point_count={point_count} < {GATE['min_point_count']}")
    return ("pass" if not reasons else "fail", reasons)


def _arm_row(spec: dict[str, str]) -> dict[str, Any]:
    metrics_path = Path(spec["metrics_path"])
    payload = _read_json(metrics_path)
    metric = _get_path(payload, spec["metrics_key"])
    gate, reasons = _gate(metric)
    return {
        "id": spec["id"],
        "label": spec["label"],
        "protocol": spec["protocol"],
        "metrics_path": str(metrics_path),
        "metrics_key": spec["metrics_key"],
        "slice_id": payload.get("slice_id"),
        "sample_count": int(metric.get("sample_count") or 0),
        "point_count": int(metric.get("point_count") or 0),
        "point_hit_agreement": float(metric.get("point_hit_agreement") or 0),
        "mean_abs_score_delta": float(metric.get("mean_abs_score_delta") or 0),
        "unsupported_judgment_count": int(metric.get("unsupported_judgment_count") or 0),
        "unsupported_judgment_rate": float(metric.get("unsupported_judgment_rate") or 0),
        "disagreement_count": _disagreement_count(metric),
        "gate": gate,
        "gate_reasons": reasons,
    }


def _baseline_rows(reference_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, label in [
        ("human_vs_artifact_first", "artifact_first baseline"),
        ("human_vs_ledger", "human_vs_ledger ceiling"),
    ]:
        metric = reference_payload[key]
        rows.append(
            {
                "id": key,
                "label": label,
                "sample_count": int(metric.get("sample_count") or 0),
                "point_count": int(metric.get("point_count") or 0),
                "point_hit_agreement": float(metric.get("point_hit_agreement") or 0),
                "mean_abs_score_delta": float(metric.get("mean_abs_score_delta") or 0),
                "disagreement_count": _disagreement_count(metric),
            }
        )
    return rows


def _consistency(arms: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    slice_ids = sorted({str(row["slice_id"]) for row in arms})
    sample_counts = sorted({int(row["sample_count"]) for row in arms})
    point_counts = sorted({int(row["point_count"]) for row in arms})
    protocols = sorted({str(row["protocol"]) for row in arms})
    return (
        {
            "same_slice": len(slice_ids) == 1,
            "slice_id": slice_ids[0] if len(slice_ids) == 1 else "",
            "sample_counts": sample_counts,
            "point_counts": point_counts,
            "same_sample_point_scope": len(sample_counts) == 1 and len(point_counts) == 1,
        },
        {
            "same_protocol": len(protocols) == 1,
            "protocols": protocols,
            "note": (
                "Current bakeoff is same human slice and scorer, but mixed prediction protocols. "
                "Use it as candidate screening; run a unified packet before runtime promotion."
                if len(protocols) > 1
                else "All arms use the same prediction protocol."
            ),
        },
    )


def _best_candidate(arms: list[dict[str, Any]]) -> dict[str, Any] | None:
    passing = [row for row in arms if row["gate"] == "pass"]
    if not passing:
        return None
    return sorted(
        passing,
        key=lambda row: (
            float(row["mean_abs_score_delta"]),
            -float(row["point_hit_agreement"]),
            int(row["unsupported_judgment_count"]),
        ),
    )[0]


def _finding(result: dict[str, Any]) -> str:
    lines = [
        "# FINDING: Luban Agentic Model Bakeoff v2 (2026-06-03)",
        "",
        "> Directional/shadow. Same human validation slice and scorer; mixed prediction protocols are explicitly marked.",
        "> 不进生产门 / 不接 RAG / 不碰 CaseGradingSkillKernel runtime。",
        "",
        "## Gate",
        "",
        f"- point_hit_agreement >= `{GATE['min_point_hit_agreement']}`",
        f"- mean_abs_score_delta <= `{GATE['max_mean_abs_score_delta']}`",
        f"- unsupported_judgment_count == `{GATE['max_unsupported_judgment_count']}`",
        f"- sample_count >= `{GATE['min_sample_count']}`; point_count >= `{GATE['min_point_count']}`",
        "",
        "## Baselines",
        "",
        "| baseline | hit_agree | delta | disagree |",
        "|---|---:|---:|---:|",
    ]
    for row in result["baselines"]:
        lines.append(
            f"| {row['label']} | {row['point_hit_agreement']:.4f} | "
            f"{row['mean_abs_score_delta']:.4f} | {row['disagreement_count']} |"
        )
    lines.extend(
        [
            "",
            "## Candidate Arms",
            "",
            "| arm | protocol | hit_agree | delta | unsupported | disagree | gate |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in result["arms"]:
        lines.append(
            f"| {row['label']} | {row['protocol']} | {row['point_hit_agreement']:.4f} | "
            f"{row['mean_abs_score_delta']:.4f} | {row['unsupported_judgment_count']} | "
            f"{row['disagreement_count']} | {row['gate']} |"
        )
    best = result.get("best_candidate") or {}
    if best:
        lines.extend(
            [
                "",
                "## Current Best Candidate",
                "",
                f"- `{best['label']}` with delta `{best['mean_abs_score_delta']:.4f}`, "
                f"hit agreement `{best['point_hit_agreement']:.4f}`, unsupported `{best['unsupported_judgment_count']}`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Protocol Readiness",
            "",
            f"- same_slice: `{result['slice_consistency']['same_slice']}`",
            f"- same_sample_point_scope: `{result['slice_consistency']['same_sample_point_scope']}`",
            f"- same_protocol: `{result['protocol_consistency']['same_protocol']}`",
            f"- note: {result['protocol_consistency']['note']}",
            "",
            "## Decision",
            "",
            "- GO: passing arms qualify for larger shadow eval.",
            "- NO-GO: no arm is approved for production runtime from this bakeoff.",
            "- Next required gate: unified typed-policy packet rerun on 50-100 answers with latency/cost capture.",
        ]
    )
    return "\n".join(lines) + "\n"


def summarize_bakeoff(*, output_dir: Path, arm_specs: list[dict[str, str]] | None = None) -> dict[str, Any]:
    specs = arm_specs or DEFAULT_ARM_SPECS
    arms = [_arm_row(spec) for spec in specs]
    reference_payload = _read_json(Path(specs[0]["metrics_path"]))
    slice_consistency, protocol_consistency = _consistency(arms)
    result = {
        "schema_version": "luban-agentic-model-bakeoff-v2",
        "status": "directional_shadow",
        "gate": GATE,
        "baselines": _baseline_rows(reference_payload),
        "arms": arms,
        "slice_consistency": slice_consistency,
        "protocol_consistency": protocol_consistency,
        "best_candidate": _best_candidate(arms),
        "production_runtime_decision": "not_approved",
        "next_gate": "larger_unified_typed_policy_shadow_eval_50_to_100_answers",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model_bakeoff_v2_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "FINDING_model_bakeoff_v2.md").write_text(_finding(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Luban agentic model bakeoff metrics.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    result = summarize_bakeoff(output_dir=Path(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
