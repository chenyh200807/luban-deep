#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_luban_human_validation_slice import score_human_labels


DEFAULT_REVIEW_PACKET = Path("artifacts/luban_human_validation_v1/po_slice_20260601/po_review_packet.json")
DEFAULT_MANIFEST = Path("artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json")
DEFAULT_LABELS = Path("artifacts/luban_human_validation_v1/po_slice_20260601/po_labels_filled.csv")

ALLOWED_HITS = {"hit", "partial", "miss"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _avg(values: list[float]) -> float:
    return round(float(mean(values)), 4) if values else 0.0


def _read_labels(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    labels: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))
        labels[key] = {
            "human_hit": str(row.get("human_hit") or "").strip(),
            "human_score": float(row.get("human_score") or 0),
            "human_note": row.get("human_note") or "",
        }
    return labels


def _compact_for_span(value: Any) -> str:
    return "".join(str(value or "").split())


def _selected_index(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(sample.get("case_id")), str(sample.get("student_id")))
        for sample in manifest.get("selected_samples") or []
    }


def _build_tasks(review_packet: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = _selected_index(manifest)
    tasks: list[dict[str, Any]] = []
    for case in review_packet.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        base = {
            "case_id": case_id,
            "question_node": case.get("question_node") or "",
            "stem": case.get("stem") or "",
            "official_answer": case.get("official_answer") or "",
            "official_analysis": case.get("official_analysis") or "",
            "penalty_rule": case.get("penalty_rule") or "",
            "scoring_points": case.get("gold_scoring_points") or [],
        }
        for sample in case.get("samples") or []:
            student_id = str(sample.get("student_id") or "")
            if (case_id, student_id) not in selected:
                continue
            tasks.append(
                {
                    **base,
                    "task_id": f"{case_id}::{student_id}",
                    "student_id": student_id,
                    "student_archetype": sample.get("archetype") or "",
                    "student_answer": sample.get("answer_text") or "",
                }
            )
    return tasks


def _student_answer_index(review_packet: dict[str, Any] | None) -> dict[tuple[str, str], str]:
    if not review_packet:
        return {}
    index: dict[tuple[str, str], str] = {}
    for case in review_packet.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        for sample in case.get("samples") or []:
            student_id = str(sample.get("student_id") or "")
            index[(case_id, student_id)] = str(sample.get("answer_text") or "")
    return index


def _prompt_text(*, packet_name: str, role: str) -> str:
    return f"""# 鲁班 Agentic Grading Harness - {role}

读取 `{packet_name}`，只根据题干、标准答案、采分点、评分规则和学生答案逐点阅卷。

硬规则：
- 不使用外部资料，不接 RAG。
- 命中必须引用学生答案原文 `evidence_span`；没有可引用原文的 hit/partial 视为 unsupported。
- 近义、大白话、口号是否给分必须按采分点 `label/list_rule/penalty_rule` 判断，并写入 `rationale`。
- 程序会计算总分；模型只输出点级 `hit/partial/miss` 与 `score`。
- 不要读取 human label、ledger 或 artifact-first 预测。

输出 JSON：
```json
{{
  "slice_id": "...",
  "prediction_sets": [
    {{
      "arm": "{role}",
      "predictions": [
        {{
          "case_id": "Q...",
          "student_id": "S...",
          "point_id": "P...",
          "hit": "hit|partial|miss",
          "score": 0,
          "confidence": 0.0,
          "evidence_span": "学生答案原文片段；miss 可为空",
          "rationale": "简短说明",
          "unsupported": false
        }}
      ]
    }}
  ]
}}
```
"""


def build_agentic_grading_packet(*, review_packet_path: Path, manifest_path: Path, output_dir: Path) -> dict[str, Path]:
    review_packet = _read_json(review_packet_path)
    manifest = _read_json(manifest_path)
    tasks = _build_tasks(review_packet, manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    packet = {
        "slice_id": review_packet.get("slice_id") or manifest.get("slice_id"),
        "status": "awaiting_model_predictions",
        "purpose": "Compare LLM/agentic point-level grading against the existing human validation slice.",
        "grading_guideline": review_packet.get("grading_guideline") or "",
        "agentic_rule": (
            "LLM handles student-answer evidence extraction and point-level adjudication; "
            "deterministic code validates schema, computes totals, and scores against human labels."
        ),
        "response_schema": {
            "prediction_sets_required_fields": ["arm", "predictions"],
            "per_point_required_fields": [
                "case_id",
                "student_id",
                "point_id",
                "hit",
                "score",
                "confidence",
                "evidence_span",
                "rationale",
                "unsupported",
            ],
            "allowed_hit_values": sorted(ALLOWED_HITS),
        },
        "tasks": tasks,
    }
    packet_path = output_dir / "agentic_grading_packet.json"
    template_path = output_dir / "agentic_predictions_template.json"
    gpt_prompt_path = output_dir / "gpt55_primary_prompt.md"
    opus_prompt_path = output_dir / "opus48_reviewer_prompt.md"
    adjudicator_prompt_path = output_dir / "dual_adjudicator_prompt.md"

    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    template_path.write_text(
        json.dumps(
            {
                "slice_id": packet["slice_id"],
                "prediction_sets": [
                    {"arm": "gpt55_primary", "predictions": []},
                    {"arm": "opus48_reviewer", "predictions": []},
                    {"arm": "dual_adjudicated", "predictions": []},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    gpt_prompt_path.write_text(_prompt_text(packet_name=packet_path.name, role="gpt55_primary"), encoding="utf-8")
    opus_prompt_path.write_text(_prompt_text(packet_name=packet_path.name, role="opus48_reviewer"), encoding="utf-8")
    adjudicator_prompt_path.write_text(
        _prompt_text(packet_name=packet_path.name, role="dual_adjudicated")
        + "\n裁决时必须比较 primary/reviewer 分歧；无学生答案证据时退 miss 或 unsupported。\n",
        encoding="utf-8",
    )
    return {
        "packet": packet_path,
        "predictions_template": template_path,
        "gpt55_primary_prompt": gpt_prompt_path,
        "opus48_reviewer_prompt": opus_prompt_path,
        "dual_adjudicator_prompt": adjudicator_prompt_path,
    }


def _expected_points(manifest: dict[str, Any]) -> dict[tuple[str, str, str], float]:
    expected: dict[tuple[str, str, str], float] = {}
    for sample in manifest.get("selected_samples") or []:
        case_id = str(sample.get("case_id"))
        student_id = str(sample.get("student_id"))
        for point in sample.get("ledger_point_rows") or []:
            expected[(case_id, student_id, str(point.get("point_id")))] = float(point.get("max_score") or 0)
    return expected


def _prediction_map(predictions: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    mapped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in predictions:
        key = (str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))
        mapped[key] = row
    return mapped


def _score_prediction_arm(
    *,
    manifest: dict[str, Any],
    labels: dict[tuple[str, str, str], dict[str, Any]],
    student_answers: dict[tuple[str, str], str] | None = None,
    arm: str,
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    pred_by_key = _prediction_map(predictions)
    expected = _expected_points(manifest)
    hit_matches: list[float] = []
    sample_deltas: list[float] = []
    disagreements: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    missing = []
    invalid = []

    sample_keys: dict[tuple[str, str], list[str]] = defaultdict(list)
    for case_id, student_id, point_id in expected:
        sample_keys[(case_id, student_id)].append(point_id)

    for key, max_score in expected.items():
        pred = pred_by_key.get(key)
        if not pred:
            missing.append({"case_id": key[0], "student_id": key[1], "point_id": key[2]})
            continue
        hit = str(pred.get("hit") or "").strip()
        if hit not in ALLOWED_HITS:
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "hit", "value": hit})
        try:
            score = float(pred.get("score"))
        except (TypeError, ValueError):
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "score", "value": pred.get("score")})
            continue
        if score < 0 or score > max_score:
            invalid.append({"case_id": key[0], "student_id": key[1], "point_id": key[2], "field": "score", "value": score, "max_score": max_score})
        evidence_span = str(pred.get("evidence_span") or "").strip()
        unsupported_reason = ""
        if hit in {"hit", "partial"} and not evidence_span:
            unsupported_reason = "missing_evidence_span"
        elif hit in {"hit", "partial"} and bool(pred.get("unsupported")):
            unsupported_reason = "model_marked_unsupported"
        elif hit in {"hit", "partial"} and student_answers:
            answer_text = student_answers.get((key[0], key[1]), "")
            if _compact_for_span(evidence_span) not in _compact_for_span(answer_text):
                unsupported_reason = "evidence_span_not_in_student_answer"
        if unsupported_reason:
            unsupported.append(
                {
                    "case_id": key[0],
                    "student_id": key[1],
                    "point_id": key[2],
                    "hit": hit,
                    "score": score,
                    "evidence_span": evidence_span,
                    "reason": unsupported_reason,
                    "rationale": pred.get("rationale") or "",
                }
            )

    completed_samples = 0
    for (case_id, student_id), point_ids in sample_keys.items():
        keys = [(case_id, student_id, point_id) for point_id in sorted(point_ids)]
        if not all(key in labels and key in pred_by_key for key in keys):
            continue
        completed_samples += 1
        human_total = 0.0
        pred_total = 0.0
        for key in keys:
            label = labels[key]
            pred = pred_by_key[key]
            human_hit = str(label.get("human_hit") or "")
            pred_hit = str(pred.get("hit") or "")
            human_score = float(label.get("human_score") or 0)
            pred_score = float(pred.get("score") or 0)
            human_total += human_score
            pred_total += pred_score
            hit_matches.append(1.0 if human_hit == pred_hit else 0.0)
            if abs(human_score - pred_score) > 1e-6 or human_hit != pred_hit:
                disagreements.append(
                    {
                        "case_id": key[0],
                        "student_id": key[1],
                        "point_id": key[2],
                        "human_hit": human_hit,
                        "target_hit": pred_hit,
                        "human_score": round(human_score, 4),
                        "target_score": round(pred_score, 4),
                        "target": arm,
                        "evidence_span": pred.get("evidence_span") or "",
                        "rationale": pred.get("rationale") or "",
                        "human_note": label.get("human_note") or "",
                    }
                )
        sample_deltas.append(abs(human_total - pred_total))

    return {
        "target": arm,
        "sample_count": completed_samples,
        "point_count": len(hit_matches),
        "mean_abs_score_delta": _avg(sample_deltas),
        "point_hit_agreement": _avg(hit_matches),
        "missing_prediction_count": len(missing),
        "invalid_prediction_count": len(invalid),
        "unsupported_judgment_rate": round(len(unsupported) / len(expected), 4) if expected else 0.0,
        "unsupported_judgment_count": len(unsupported),
        "unsupported_judgments": unsupported,
        "missing_predictions": missing,
        "invalid_predictions": invalid,
        "disagreements": disagreements,
    }


def score_agentic_predictions(
    *,
    manifest_path: Path,
    labels_path: Path,
    predictions_path: Path,
    review_packet_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    labels = _read_labels(labels_path)
    predictions_payload = _read_json(predictions_path)
    review_packet = _read_json(review_packet_path) if review_packet_path else None
    student_answers = _student_answer_index(review_packet)
    baseline = score_human_labels(manifest_path=manifest_path, labels_path=labels_path)
    agentic_arms: dict[str, Any] = {}
    for prediction_set in predictions_payload.get("prediction_sets") or []:
        arm = str(prediction_set.get("arm") or "").strip()
        if not arm:
            continue
        agentic_arms[arm] = _score_prediction_arm(
            manifest=manifest,
            labels=labels,
            student_answers=student_answers,
            arm=arm,
            predictions=prediction_set.get("predictions") or [],
        )
    return {
        "slice_id": manifest.get("slice_id"),
        "predictions_file": str(predictions_path),
        "human_vs_artifact_first": baseline["human_vs_artifact_first"],
        "human_vs_ledger": baseline["human_vs_ledger"],
        "agentic_arms": agentic_arms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or score Luban agentic grading harness packets.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--review-packet", default=str(DEFAULT_REVIEW_PACKET))
    build.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    build.add_argument("--output-dir", required=True)
    score = sub.add_parser("score")
    score.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    score.add_argument("--labels", default=str(DEFAULT_LABELS))
    score.add_argument("--review-packet", default=str(DEFAULT_REVIEW_PACKET))
    score.add_argument("--predictions", required=True)
    score.add_argument("--output")
    args = parser.parse_args()

    if args.command == "build":
        paths = build_agentic_grading_packet(
            review_packet_path=Path(args.review_packet),
            manifest_path=Path(args.manifest),
            output_dir=Path(args.output_dir),
        )
        print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
        return 0

    result = score_agentic_predictions(
        manifest_path=Path(args.manifest),
        labels_path=Path(args.labels),
        predictions_path=Path(args.predictions),
        review_packet_path=Path(args.review_packet) if args.review_packet else None,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
