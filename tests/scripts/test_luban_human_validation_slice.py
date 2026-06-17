from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_luban_human_validation_slice import (
    DEFAULT_FIXTURE,
    build_validation_bundle,
    select_validation_slice,
)
from scripts.score_luban_human_validation_slice import parse_review_book_markdown, score_human_labels, validate_human_labels


def _gold_point_rows(case: dict, sample: dict) -> list[dict]:
    points_by_id = {str(point.get("point_id")): point for point in case.get("gold_scoring_points") or []}
    rows: list[dict] = []
    for hit_row in (sample.get("ground_truth_ledger") or {}).get("point_hits") or []:
        point_id = str(hit_row.get("point_id") or "")
        point = points_by_id.get(point_id) or {}
        max_score = float(point.get("max_score") or 0)
        hit = str(hit_row.get("hit") or "")
        gold_score = max_score if hit == "hit" else (max_score / 2 if hit == "partial" else 0.0)
        rows.append(
            {
                "point_id": point_id,
                "max_score": max_score,
                "ledger_hit": hit,
                "gold_score": gold_score,
            }
        )
    return rows


def _write_after_report_fixture(tmp_path: Path) -> Path:
    fixture = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    cases = fixture["cases"][:3]
    rows = []
    reasons = [
        {"score_delta": 1.0, "gold_penalty_triggered": False, "case_group_tags": []},
        {"score_delta": 0.0, "gold_penalty_triggered": True, "case_group_tags": ["penalty_rule"]},
        {"score_delta": -1.0, "gold_penalty_triggered": False, "case_group_tags": []},
    ]
    for case, reason in zip(cases, reasons, strict=True):
        sample = (case.get("eval_samples") or [])[0]
        gold_rows = _gold_point_rows(case, sample)
        rows.append(
            {
                "arm": "artifact_first",
                "case_id": case["case_id"],
                "sample_id": sample["student_id"],
                "gold_score": sum(float(row["gold_score"]) for row in gold_rows),
                "pred_score": 0.0,
                "score_delta": reason["score_delta"],
                "gold_penalty_triggered": reason["gold_penalty_triggered"],
                "case_group_tags": reason["case_group_tags"],
                "gold_point_rows": gold_rows,
                "result": {
                    "rubric_items": [
                        {"criterion": f"{row['point_id']}::fixture", "awarded_score": row["gold_score"]}
                        for row in gold_rows
                    ]
                },
            }
        )
    report_path = tmp_path / "after_report.json"
    report_path.write_text(json.dumps({"rows": rows, "artifact_weaknesses": {}}, ensure_ascii=False), encoding="utf-8")
    return report_path


def test_select_validation_slice_is_blind_and_includes_error_frontier(tmp_path: Path) -> None:
    report_path = _write_after_report_fixture(tmp_path)
    bundle = select_validation_slice(
        fixture_path=DEFAULT_FIXTURE,
        report_path=report_path,
        target_count=24,
    )

    selected = bundle["selected_samples"]
    assert 1 <= len(selected) <= 24
    assert any(sample["selection_reason"] == "positive_score_delta" for sample in selected)
    assert any(sample["selection_reason"] == "penalty_rule_case" for sample in selected)
    assert any(sample["selection_reason"] == "largest_under_score_delta" for sample in selected)

    public_packet = bundle["po_review_packet"]
    serialized_public = json.dumps(public_packet, ensure_ascii=False)
    assert "pred_score" not in serialized_public
    assert "artifact-first" not in serialized_public
    assert "artifact_first" not in serialized_public
    assert "baseline" not in serialized_public
    assert "RAG" not in serialized_public
    assert "ground_truth_ledger" not in serialized_public
    assert "blind_grade" not in serialized_public
    assert public_packet["review_status"] == "awaiting_human_labels"


def test_build_validation_bundle_writes_protocol_packet_and_label_templates(tmp_path: Path) -> None:
    report_path = _write_after_report_fixture(tmp_path)
    paths = build_validation_bundle(
        fixture_path=DEFAULT_FIXTURE,
        report_path=report_path,
        output_dir=tmp_path,
        target_count=12,
    )

    assert paths["po_review_packet"].exists()
    assert paths["po_labels_template_csv"].exists()
    assert paths["po_labels_template_json"].exists()
    assert paths["internal_manifest"].exists()
    assert paths["protocol"].exists()

    packet = json.loads(paths["po_review_packet"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["internal_manifest"].read_text(encoding="utf-8"))
    assert packet["slice_id"] == manifest["slice_id"]
    assert manifest["artifact_assets"]
    assert all("content_hash" in asset for asset in manifest["artifact_assets"])

    rows = list(csv.DictReader(paths["po_labels_template_csv"].open(encoding="utf-8")))
    assert rows
    assert {"case_id", "student_id", "point_id", "human_hit", "human_score"} <= set(rows[0])
    assert all(row["human_hit"] == "" for row in rows)


def test_score_human_labels_compares_human_to_ledger_and_artifact(tmp_path: Path) -> None:
    report_path = _write_after_report_fixture(tmp_path)
    paths = build_validation_bundle(
        fixture_path=DEFAULT_FIXTURE,
        report_path=report_path,
        output_dir=tmp_path,
        target_count=3,
    )
    manifest = json.loads(paths["internal_manifest"].read_text(encoding="utf-8"))
    label_rows: list[dict[str, str]] = []
    for sample in manifest["selected_samples"]:
        for point in sample["ledger_point_rows"]:
            label_rows.append(
                {
                    "case_id": sample["case_id"],
                    "student_id": sample["student_id"],
                    "point_id": point["point_id"],
                    "human_hit": point["ledger_hit"],
                    "human_score": str(point["gold_score"]),
                    "human_error_codes": "",
                    "human_note": "test fixture mirrors ledger",
                }
            )
    labels_path = tmp_path / "human_labels.csv"
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(label_rows[0]))
        writer.writeheader()
        writer.writerows(label_rows)

    result = score_human_labels(manifest_path=paths["internal_manifest"], labels_path=labels_path)

    assert result["human_vs_ledger"]["mean_abs_score_delta"] == 0.0
    assert result["human_vs_ledger"]["point_hit_agreement"] == 1.0
    assert result["human_vs_artifact_first"]["sample_count"] == len(manifest["selected_samples"])


def test_parse_review_book_markdown_extracts_teacher_rows() -> None:
    markdown = """
# 1. QX （满分 1 分）
### 学生 S1
**给 S1 打分**:

| 采分点 | 满分 | 判定(hit/partial/miss) | 得分 | 备注 |
|---|---|---|---|---|
| P1 | 1 | partial | 0.5 | 老师备注 |
"""

    rows = parse_review_book_markdown(markdown)

    assert rows == [
        {
            "case_id": "QX",
            "student_id": "S1",
            "point_id": "P1",
            "human_hit": "partial",
            "human_score": "0.5",
            "human_note": "老师备注",
            "human_error_codes": "",
        }
    ]


def test_validate_human_labels_reports_missing_and_invalid_without_guessing(tmp_path: Path) -> None:
    manifest = {
        "selected_samples": [
            {
                "case_id": "QX",
                "student_id": "S1",
                "ledger_point_rows": [
                    {"point_id": "P1", "max_score": 1},
                    {"point_id": "P2", "max_score": 0.5},
                ],
            }
        ]
    }
    labels = {
        ("QX", "S1", "P1"): {
            "human_hit": "yes",
            "human_score": 2.0,
            "human_note": "",
            "human_error_codes": "",
        }
    }

    validation = validate_human_labels(manifest=manifest, labels=labels)

    assert validation["filled_label_count"] == 1
    assert validation["missing_count"] == 1
    assert validation["invalid_count"] == 2
