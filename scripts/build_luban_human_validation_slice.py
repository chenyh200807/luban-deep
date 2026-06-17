#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.poc_luban_case_grading_three_arms import compile_kernel_scoring_points, compile_penalty_rules  # noqa: E402

DEFAULT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_AFTER_REPORT = (
    PROJECT_ROOT
    / "artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_185157.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/luban_human_validation_v1/po_slice_20260601"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _artifact_point_scores(result: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for item in result.get("rubric_items") or []:
        criterion = str(item.get("criterion") or "")
        if "::" not in criterion:
            continue
        point_id = criterion.split("::", 1)[0]
        scores[point_id] += float(item.get("awarded_score") or 0)
    return {key: round(value, 4) for key, value in scores.items()}


def _weakness_lookup(report: dict[str, Any]) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    weaknesses = report.get("artifact_weaknesses") if isinstance(report.get("artifact_weaknesses"), dict) else {}
    for bucket in ("over_scored", "under_scored"):
        for row in weaknesses.get(bucket) or []:
            lookup[(str(row.get("case_id")), str(row.get("sample_id")))] = str(row.get("category") or "")
    return lookup


def _ordered_case_lookup(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(case.get("case_id")): case for case in fixture.get("cases") or []}


def _sample_lookup(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(sample.get("student_id")): sample for sample in case.get("eval_samples") or []}


def _source_hashes(fixture_path: Path, report_path: Path) -> dict[str, str]:
    return {
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "after_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
    }


def _selection_reason(row: dict[str, Any], weakness_category: str) -> str:
    if float(row.get("score_delta") or 0) > 0:
        return "positive_score_delta"
    if row.get("gold_penalty_triggered") or "penalty_rule" in (row.get("case_group_tags") or []):
        return "penalty_rule_case"
    if weakness_category:
        return weakness_category
    return "largest_under_score_delta"


def _select_rows(report: dict[str, Any], *, target_count: int) -> list[dict[str, Any]]:
    artifact_rows = [row for row in report.get("rows") or [] if row.get("arm") == "artifact_first"]
    weakness = _weakness_lookup(report)
    keyed: dict[tuple[str, str], dict[str, Any]] = {}

    def add(row: dict[str, Any], reason: str) -> None:
        key = (str(row.get("case_id")), str(row.get("sample_id")))
        if key not in keyed:
            keyed[key] = {**row, "selection_reason": reason, "weakness_category": weakness.get(key, "")}

    for row in sorted(artifact_rows, key=lambda item: (str(item.get("case_id")), str(item.get("sample_id")))):
        if float(row.get("score_delta") or 0) > 0:
            add(row, "positive_score_delta")
    for row in sorted(artifact_rows, key=lambda item: (str(item.get("case_id")), str(item.get("sample_id")))):
        if row.get("gold_penalty_triggered") or "penalty_rule" in (row.get("case_group_tags") or []):
            add(row, "penalty_rule_case")
    for row in sorted(artifact_rows, key=lambda item: abs(float(item.get("score_delta") or 0)), reverse=True):
        if len(keyed) >= target_count:
            break
        add(row, "largest_under_score_delta" if float(row.get("score_delta") or 0) < 0 else _selection_reason(row, weakness.get((str(row.get("case_id")), str(row.get("sample_id"))), "")))

    return list(keyed.values())[:target_count]


def _public_scoring_points(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "point_id": point.get("point_id"),
            "label": point.get("label"),
            "max_score": point.get("max_score"),
            "official_basis": point.get("official_basis"),
            "list_rule": point.get("list_rule"),
            "penalty_rule": point.get("penalty_rule"),
        }
        for point in case.get("gold_scoring_points") or []
    ]


def select_validation_slice(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    report_path: Path = DEFAULT_AFTER_REPORT,
    target_count: int = 24,
) -> dict[str, Any]:
    fixture = _read_json(fixture_path)
    report = _read_json(report_path)
    cases = _ordered_case_lookup(fixture)
    selected_rows = _select_rows(report, target_count=target_count)
    slice_id = f"luban-human-v1-{target_count}-{_hash_payload([(r['case_id'], r['sample_id']) for r in selected_rows])[:12]}"

    selected_samples: list[dict[str, Any]] = []
    public_cases: dict[str, dict[str, Any]] = {}
    artifact_assets: list[dict[str, Any]] = []

    for row in selected_rows:
        case_id = str(row.get("case_id"))
        student_id = str(row.get("sample_id"))
        case = cases[case_id]
        sample = _sample_lookup(case)[student_id]
        compiled_points = compile_kernel_scoring_points(case)
        penalty_rules = compile_penalty_rules(case)
        asset_payload = {"scoring_points": compiled_points, "penalty_rules": penalty_rules}
        artifact_assets.append(
            {
                "case_id": case_id,
                "schema_version": "grading_artifact.v1",
                "version_id": f"{case_id}:{_hash_payload(asset_payload)[:16]}",
                "content_hash": _hash_payload(asset_payload),
                "source_authority": "golden.gold_scoring_points + golden.penalty_rule",
                "compiled_scoring_point_count": len(compiled_points),
                "penalty_rule_count": len(penalty_rules),
            }
        )
        selected_samples.append(
            {
                "case_id": case_id,
                "student_id": student_id,
                "selection_reason": row["selection_reason"],
                "weakness_category": row.get("weakness_category") or "",
                "case_group_tags": row.get("case_group_tags") or [],
                "archetype": sample.get("archetype"),
                "ledger_score": row.get("gold_score"),
                "artifact_score": row.get("pred_score"),
                "artifact_point_scores": _artifact_point_scores(row.get("result") or {}),
                "ledger_point_rows": row.get("gold_point_rows") or [],
            }
        )
        public_case = public_cases.setdefault(
            case_id,
            {
                "case_id": case_id,
                "question_node": case.get("question_node"),
                "max_score": case.get("max_score"),
                "stem": case.get("stem"),
                "official_answer": case.get("official_answer"),
                "official_analysis": case.get("official_analysis"),
                "penalty_rule": case.get("penalty_rule"),
                "gold_scoring_points": _public_scoring_points(case),
                "samples": [],
            },
        )
        public_case["samples"].append(
            {
                "student_id": student_id,
                "archetype": sample.get("archetype"),
                "answer_text": sample.get("answer_text"),
            }
        )

    public_packet = {
        "slice_id": slice_id,
        "review_status": "awaiting_human_labels",
        "exam_scope": fixture.get("exam_scope"),
        "grading_guideline": fixture.get("grading_guideline"),
        "blind_review_rule": "Review only the question, official answer, scoring points, and student answer. Do not consult any prior labels or model predictions.",
        "cases": list(public_cases.values()),
    }
    return {
        "slice_id": slice_id,
        "source_hashes": _source_hashes(fixture_path, report_path),
        "po_review_packet": public_packet,
        "selected_samples": selected_samples,
        "artifact_assets": artifact_assets,
    }


def _label_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in packet["cases"]:
        for sample in case["samples"]:
            for point in case["gold_scoring_points"]:
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "student_id": sample["student_id"],
                        "point_id": point["point_id"],
                        "max_score": point["max_score"],
                        "point_label": point["label"],
                        "human_hit": "",
                        "human_score": "",
                        "human_error_codes": "",
                        "human_note": "",
                    }
                )
    return rows


def build_validation_bundle(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    report_path: Path = DEFAULT_AFTER_REPORT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    target_count: int = 24,
) -> dict[str, Path]:
    bundle = select_validation_slice(fixture_path=fixture_path, report_path=report_path, target_count=target_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "po_review_packet.json"
    manifest_path = output_dir / "internal_slice_manifest.json"
    csv_path = output_dir / "po_labels_template.csv"
    json_template_path = output_dir / "po_labels_template.json"
    protocol_path = output_dir / "human_validation_protocol.md"

    packet_path.write_text(json.dumps(bundle["po_review_packet"], ensure_ascii=False, indent=2), encoding="utf-8")
    internal_manifest = {
        "slice_id": bundle["slice_id"],
        "status": "awaiting_human_labels",
        "source_hashes": bundle["source_hashes"],
        "selected_samples": bundle["selected_samples"],
        "artifact_assets": bundle["artifact_assets"],
    }
    manifest_path.write_text(json.dumps(internal_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = _label_rows(bundle["po_review_packet"])
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_template_path.write_text(json.dumps({"slice_id": bundle["slice_id"], "labels": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    protocol_path.write_text(_protocol_markdown(bundle), encoding="utf-8")
    return {
        "po_review_packet": packet_path,
        "po_labels_template_csv": csv_path,
        "po_labels_template_json": json_template_path,
        "internal_manifest": manifest_path,
        "protocol": protocol_path,
    }


def _protocol_markdown(bundle: dict[str, Any]) -> str:
    return f"""# 鲁班案例题 v1 PO 人锚定校验协议

Slice: `{bundle['slice_id']}`

## 定性

这是 v1 validation slice 的人工校验包。v0 gold 仍然是 `ground_truth_ledger`，本切片新增 PO / 真人标签作为更高权威校验层，用于衡量 ledger 本身是否可信。不得用 AI 代替真人填写。

## 盲标规则

- PO 只看 `po_review_packet.json` 与题目、学生答案、官方答案、采分点。
- 不展示 baseline / RAG / artifact-first 的预测。
- 不展示 `ground_truth_ledger` 或 `blind_grade`。
- 按踩字口径判定：命中 = 写出教材/官方术语原文；近义、口号、大白话不算。

## 填写方式

填写 `po_labels_template.csv`：

- `human_hit`: `hit` / `partial` / `miss`
- `human_score`: 该采分点人工给分，范围 `0..max_score`
- `human_error_codes`: 可空，多个用 `;` 分隔
- `human_note`: 必要时写分歧原因

## 回收后度量

运行：

```bash
python scripts/score_luban_human_validation_slice.py \\
  --manifest artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json \\
  --labels artifacts/luban_human_validation_v1/po_slice_20260601/po_labels_filled.csv \\
  --output artifacts/luban_human_validation_v1/po_slice_20260601/human_validation_metrics.json
```

输出会比较：

- human-vs-ledger：衡量 AI-ledger 可信度。
- human-vs-artifact-first：衡量 grader 对真人标签的真实准确率。
- disagreement samples：供后续根因分析。

## 红线

该切片不是生产门。没有真人填写前，不得声明人锚定结果。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Luban v1 human validation slice bundle.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--report", default=str(DEFAULT_AFTER_REPORT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--target-count", type=int, default=24)
    args = parser.parse_args()
    paths = build_validation_bundle(
        fixture_path=Path(args.fixture),
        report_path=Path(args.report),
        output_dir=Path(args.output_dir),
        target_count=args.target_count,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
