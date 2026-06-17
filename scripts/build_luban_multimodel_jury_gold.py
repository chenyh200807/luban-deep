#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_OUTPUT_DIR = Path("artifacts/luban_agentic_grading_harness/multimodel_jury_gold_20260603")
DEFAULT_MANIFEST = Path("artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json")
DEFAULT_LABELS = Path("artifacts/luban_human_validation_v1/po_slice_20260601/po_labels_filled.csv")

DEFAULT_ARM_SPECS = [
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_predictions_filled.json:gpt55_primary:gpt55",
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_predictions_filled.json:opus48_reviewer:opus48",
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603/deepseek_predictions_span_guarded.json:deepseek_v4_flash_primary:deepseek_v4_flash",
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_crossmodel_qwen_20260603/crossmodel_predictions.json:qwen_primary:qwen37",
]

ALLOWED_HITS = {"hit", "partial", "miss"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _avg(values: list[float]) -> float:
    return round(float(mean(values)), 4) if values else 0.0


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))


def _load_prediction_set(path: Path, arm: str) -> list[dict[str, Any]]:
    payload = _read_json(path)
    for prediction_set in payload.get("prediction_sets") or []:
        if str(prediction_set.get("arm")) == arm:
            return list(prediction_set.get("predictions") or [])
    raise ValueError(f"arm {arm!r} not found in {path}")


def _parse_arm_spec(spec: str) -> tuple[Path, str, str]:
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError("arm spec must be '<predictions_json>:<arm>:<alias>'")
    return Path(parts[0]), parts[1], parts[2]


def _prediction_signature(row: dict[str, Any]) -> tuple[str, float]:
    hit = str(row.get("hit") or "").strip()
    if hit not in ALLOWED_HITS:
        hit = "miss"
    return hit, round(float(row.get("score") or 0), 4)


def _is_supported(row: dict[str, Any]) -> bool:
    hit, score = _prediction_signature(row)
    if bool(row.get("unsupported")):
        return False
    if hit in {"hit", "partial"} or score > 0:
        return bool(str(row.get("evidence_span") or "").strip())
    return True


def _expected_keys(manifest_path: Path | None) -> list[tuple[str, str, str]]:
    if not manifest_path or not manifest_path.exists():
        return []
    manifest = _read_json(manifest_path)
    keys: list[tuple[str, str, str]] = []
    for sample in manifest.get("selected_samples") or []:
        for point in sample.get("ledger_point_rows") or []:
            keys.append((str(sample.get("case_id")), str(sample.get("student_id")), str(point.get("point_id"))))
    return keys


def _read_labels(labels_path: Path | None) -> dict[tuple[str, str, str], tuple[str, float]]:
    if not labels_path or not labels_path.exists():
        return {}
    rows = list(csv.DictReader(labels_path.open(encoding="utf-8")))
    labels: dict[tuple[str, str, str], tuple[str, float]] = {}
    for row in rows:
        hit = str(row.get("human_hit") or "").strip()
        score_raw = str(row.get("human_score") or "").strip()
        if not hit or not score_raw:
            continue
        labels[(str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))] = (hit, round(float(score_raw), 4))
    return labels


def _pairwise_agreement(arm_predictions: dict[str, dict[tuple[str, str, str], dict[str, Any]]], keys: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    arms = sorted(arm_predictions)
    rows: list[dict[str, Any]] = []
    for index, left in enumerate(arms):
        for right in arms[index + 1 :]:
            compared = 0
            hit_matches = 0
            score_matches = 0
            for key in keys:
                if key not in arm_predictions[left] or key not in arm_predictions[right]:
                    continue
                compared += 1
                left_sig = _prediction_signature(arm_predictions[left][key])
                right_sig = _prediction_signature(arm_predictions[right][key])
                hit_matches += int(left_sig[0] == right_sig[0])
                score_matches += int(left_sig == right_sig)
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "compared": compared,
                    "hit_agreement": round(hit_matches / compared, 4) if compared else 0.0,
                    "hit_score_agreement": round(score_matches / compared, 4) if compared else 0.0,
                }
            )
    return rows


def _compare_candidate_to_gold(
    *,
    target_arm: str,
    gold_rows: list[dict[str, Any]],
    arm_predictions: dict[str, dict[tuple[str, str, str], dict[str, Any]]],
) -> dict[str, Any]:
    hit_matches: list[float] = []
    score_deltas: list[float] = []
    disagreements: list[dict[str, Any]] = []
    for gold in gold_rows:
        key = (gold["case_id"], gold["student_id"], gold["point_id"])
        pred = arm_predictions.get(target_arm, {}).get(key)
        if not pred:
            continue
        pred_hit, pred_score = _prediction_signature(pred)
        gold_hit = str(gold["jury_hit"])
        gold_score = float(gold["jury_score"])
        hit_matches.append(1.0 if pred_hit == gold_hit else 0.0)
        score_deltas.append(abs(pred_score - gold_score))
        if pred_hit != gold_hit or abs(pred_score - gold_score) > 1e-6:
            disagreements.append(
                {
                    "case_id": key[0],
                    "student_id": key[1],
                    "point_id": key[2],
                    "target_hit": pred_hit,
                    "target_score": pred_score,
                    "jury_hit": gold_hit,
                    "jury_score": gold_score,
                    "target_rationale": pred.get("rationale") or "",
                }
            )
    return {
        "target_arm": target_arm,
        "jury_point_count": len(hit_matches),
        "point_hit_agreement": _avg(hit_matches),
        "mean_abs_point_score_delta": _avg(score_deltas),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }


def _frontier_queue_rows(frontier_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frontier_rows:
        arms = row.get("arms") or {}
        signatures = sorted({(value.get("hit"), value.get("score")) for value in arms.values()})
        rows.append(
            {
                "case_id": row["case_id"],
                "student_id": row["student_id"],
                "point_id": row["point_id"],
                "top_hit": row.get("top_hit"),
                "top_score": row.get("top_score"),
                "top_vote_count": row.get("top_vote_count"),
                "distinct_judgments": len(signatures),
                "unsupported_arms": ",".join(row.get("unsupported_arms") or []),
                "arm_judgments": " | ".join(
                    f"{arm}:{value.get('hit')}/{value.get('score')}" for arm, value in sorted(arms.items())
                ),
            }
        )
    return rows


def _compare_gold_to_human(*, gold_rows: list[dict[str, Any]], labels: dict[tuple[str, str, str], tuple[str, float]]) -> dict[str, Any]:
    hit_matches: list[float] = []
    score_deltas: list[float] = []
    disagreements: list[dict[str, Any]] = []
    for gold in gold_rows:
        key = (gold["case_id"], gold["student_id"], gold["point_id"])
        if key not in labels:
            continue
        human_hit, human_score = labels[key]
        jury_hit = str(gold["jury_hit"])
        jury_score = float(gold["jury_score"])
        hit_matches.append(1.0 if human_hit == jury_hit else 0.0)
        score_deltas.append(abs(human_score - jury_score))
        if human_hit != jury_hit or abs(human_score - jury_score) > 1e-6:
            disagreements.append(
                {
                    "case_id": key[0],
                    "student_id": key[1],
                    "point_id": key[2],
                    "human_hit": human_hit,
                    "human_score": human_score,
                    "jury_hit": jury_hit,
                    "jury_score": jury_score,
                }
            )
    return {
        "point_count": len(hit_matches),
        "point_hit_agreement": _avg(hit_matches),
        "mean_abs_point_score_delta": _avg(score_deltas),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }


def _finding(result: dict[str, Any]) -> str:
    summary = result["summary"]
    target = result.get("target_vs_jury") or {}
    lines = [
        "# FINDING: Luban Multi-model Jury Gold",
        "",
        "> Directional/shadow. This is an offline official-standard-anchored jury analysis, not production approval.",
        "",
        "## Summary",
        "",
        f"- total points: `{summary['total_points']}`",
        f"- full consensus points: `{summary['full_consensus_points']}`",
        f"- frontier points: `{summary['frontier_points']}`",
        f"- unsupported-positive points: `{summary['unsupported_positive_points']}`",
        "",
    ]
    if target:
        lines.extend(
            [
                "## Target vs Leave-one-out Jury",
                "",
                f"- target arm: `{target['target_arm']}`",
                f"- jury points: `{target['jury_point_count']}`",
                f"- point hit agreement: `{target['point_hit_agreement']:.4f}`",
                f"- mean abs point score delta: `{target['mean_abs_point_score_delta']:.4f}`",
                f"- disagreements: `{target['disagreement_count']}`",
                "",
            ]
        )
    human = result.get("human_checks") or {}
    if human.get("jury_vs_human"):
        check = human["jury_vs_human"]
        lines.extend(
            [
                "## Human Slice Check",
                "",
                f"- jury points checked: `{check['point_count']}`",
                f"- jury-vs-human hit agreement: `{check['point_hit_agreement']:.4f}`",
                f"- jury-vs-human mean abs point score delta: `{check['mean_abs_point_score_delta']:.4f}`",
                f"- disagreements: `{check['disagreement_count']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "- Full consensus rows are high-confidence synthetic gold candidates because heterogeneous models independently reached the same point-level judgment.",
            "- Frontier rows are the real calibration queue; do not hide them inside automatic metrics.",
            "- If the target arm is part of the model set, the target comparison uses a leave-one-out jury to avoid circular scoring.",
            "",
        ]
    )
    return "\n".join(lines)


def run_jury_analysis(
    *,
    manifest_path: Path | None,
    labels_path: Path | None,
    arm_specs: list[str],
    target_arm: str,
    output_dir: Path,
) -> dict[str, Any]:
    arm_predictions: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
    for spec in arm_specs:
        path, arm, alias = _parse_arm_spec(spec)
        rows = _load_prediction_set(path, arm)
        arm_predictions[alias] = {_key(row): row for row in rows}

    keys = _expected_keys(manifest_path)
    if not keys:
        keys = sorted(set().union(*(set(rows) for rows in arm_predictions.values())))

    consensus_rows: list[dict[str, Any]] = []
    frontier_rows: list[dict[str, Any]] = []
    unsupported_positive_points = 0
    for key in keys:
        present = {arm: rows[key] for arm, rows in arm_predictions.items() if key in rows}
        signatures = {arm: _prediction_signature(row) for arm, row in present.items()}
        unsupported_arms = [
            arm
            for arm, row in present.items()
            if not _is_supported(row) and (_prediction_signature(row)[0] in {"hit", "partial"} or _prediction_signature(row)[1] > 0)
        ]
        if unsupported_arms:
            unsupported_positive_points += 1
        sig_counts = Counter(signatures.values())
        top_signature, top_count = sig_counts.most_common(1)[0] if sig_counts else (("miss", 0.0), 0)
        row = {
            "case_id": key[0],
            "student_id": key[1],
            "point_id": key[2],
            "arms": {
                arm: {
                    "hit": signatures[arm][0],
                    "score": signatures[arm][1],
                    "supported": _is_supported(pred),
                    "evidence_span": pred.get("evidence_span") or "",
                    "rationale": pred.get("rationale") or "",
                }
                for arm, pred in present.items()
            },
            "unsupported_arms": unsupported_arms,
        }
        if len(present) == len(arm_predictions) and top_count == len(arm_predictions) and not unsupported_arms:
            row.update({"jury_hit": top_signature[0], "jury_score": top_signature[1], "consensus_type": "full"})
            consensus_rows.append(row)
        else:
            row.update({"top_hit": top_signature[0], "top_score": top_signature[1], "top_vote_count": top_count})
            frontier_rows.append(row)

    jury_rows_for_target = []
    if target_arm in arm_predictions:
        non_target_arms = {arm: rows for arm, rows in arm_predictions.items() if arm != target_arm}
        for key in keys:
            present = {arm: rows[key] for arm, rows in non_target_arms.items() if key in rows}
            if len(present) != len(non_target_arms):
                continue
            signatures = {arm: _prediction_signature(row) for arm, row in present.items()}
            unsupported = [
                arm
                for arm, row in present.items()
                if not _is_supported(row) and (_prediction_signature(row)[0] in {"hit", "partial"} or _prediction_signature(row)[1] > 0)
            ]
            sig_counts = Counter(signatures.values())
            top_signature, top_count = sig_counts.most_common(1)[0]
            if top_count == len(non_target_arms) and not unsupported:
                jury_rows_for_target.append(
                    {
                        "case_id": key[0],
                        "student_id": key[1],
                        "point_id": key[2],
                        "jury_hit": top_signature[0],
                        "jury_score": top_signature[1],
                        "jury_arms": sorted(non_target_arms),
                    }
                )

    labels = _read_labels(labels_path)
    result = {
        "schema_version": "luban-multimodel-jury-gold.v0.1",
        "arms": sorted(arm_predictions),
        "target_arm": target_arm,
        "summary": {
            "total_points": len(keys),
            "full_consensus_points": len(consensus_rows),
            "frontier_points": len(frontier_rows),
            "unsupported_positive_points": unsupported_positive_points,
            "full_consensus_rate": round(len(consensus_rows) / len(keys), 4) if keys else 0.0,
        },
        "pairwise_agreement": _pairwise_agreement(arm_predictions, keys),
        "target_vs_jury": _compare_candidate_to_gold(target_arm=target_arm, gold_rows=jury_rows_for_target, arm_predictions=arm_predictions)
        if target_arm in arm_predictions
        else None,
        "human_checks": {
            "jury_vs_human": _compare_gold_to_human(gold_rows=jury_rows_for_target, labels=labels) if labels else None,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "multimodel_jury_summary.json", result)
    _write_json(output_dir / "jury_consensus_points.json", consensus_rows)
    _write_json(output_dir / "jury_frontier_points.json", frontier_rows)
    _write_json(output_dir / "leave_one_out_jury_points_for_target.json", jury_rows_for_target)
    _write_csv(
        output_dir / "jury_frontier_queue.csv",
        _frontier_queue_rows(frontier_rows),
        [
            "case_id",
            "student_id",
            "point_id",
            "top_hit",
            "top_score",
            "top_vote_count",
            "distinct_judgments",
            "unsupported_arms",
            "arm_judgments",
        ],
    )
    _write_csv(
        output_dir / "target_disagreements.csv",
        (result.get("target_vs_jury") or {}).get("disagreements") or [],
        [
            "case_id",
            "student_id",
            "point_id",
            "target_hit",
            "target_score",
            "jury_hit",
            "jury_score",
            "target_rationale",
        ],
    )
    (output_dir / "FINDING_multimodel_jury_gold.md").write_text(_finding(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline heterogeneous-model jury gold analysis for Luban grading.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--arm", action="append", dest="arms", help="Format: <predictions_json>:<arm>:<alias>")
    parser.add_argument("--target-arm", default="qwen37")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    result = run_jury_analysis(
        manifest_path=Path(args.manifest) if args.manifest else None,
        labels_path=Path(args.labels) if args.labels else None,
        arm_specs=args.arms or DEFAULT_ARM_SPECS,
        target_arm=args.target_arm,
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
