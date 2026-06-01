from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_no_human_v1_5_golden import build_no_human_v1_5_bundle


def test_build_no_human_v1_5_bundle_writes_auditable_fixture(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text(
        json.dumps({"content": "施工总进度计划表（图），资源需要量及供应平衡表。"}, ensure_ascii=False),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "exam_scope": "一级建造师建筑实务",
        "grading_guideline": "踩字",
        "cases": [
            {
                "case_id": "Q1",
                "question_node": "1A000000",
                "max_score": 2,
                "stem": "写出施工总进度计划缺项。",
                "official_answer": "施工总进度计划表（图）、资源需要量及供应平衡表。",
                "official_analysis": "",
                "penalty_rule": "",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出'施工总进度计划表(图)''资源需要量及供应平衡表'。",
                        "max_score": 2,
                        "official_basis": "施工总进度计划表（图），资源需要量及供应平衡表。",
                    }
                ],
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "answer_text": "施工总进度计划表（图）",
                        "ground_truth_ledger": {"point_hits": [{"point_id": "P1", "hit": "partial"}]},
                    }
                ],
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

    result = build_no_human_v1_5_bundle(
        fixture_path=fixture_path,
        source_root=source_root,
        output_fixture_path=tmp_path / "golden_no_human.json",
        output_dir=tmp_path / "artifacts",
        prior_report_path=None,
    )

    output_fixture = json.loads(Path(result["fixture_path"]).read_text(encoding="utf-8"))
    point = output_fixture["cases"][0]["gold_scoring_points"][0]
    label = output_fixture["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"][0]
    assert output_fixture["suite"] == "luban_case_grading_golden_no_human_v1_5"
    assert output_fixture["golden_layer"]["name"] == "textbook_anchored_auditable_no_human_v1_5"
    assert point["textbook_provenance"]["terms"][0]["anchors"]
    assert label["is_deterministic"] is True
    assert result["summary"]["samples"] == 1


def test_build_no_human_v1_5_recovers_label_terms_from_official_answer_after_junk_raw_terms(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text("{}", encoding="utf-8")
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q11",
                "official_answer": "①生活区；②办公区；③材料加工和存放区；每项1分。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "施工现场封闭管理'四区'除施工区外的另外三区,必须写出规范术语:生活区、办公区、材料加工和存放区(三项列举)",
                        "max_score": 3,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "生活区、办公区、材料加工和存放区"}],
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

    result = build_no_human_v1_5_bundle(
        fixture_path=fixture_path,
        source_root=source_root,
        output_fixture_path=tmp_path / "golden_no_human.json",
        output_dir=tmp_path / "artifacts",
        prior_report_path=None,
    )

    output_fixture = json.loads(Path(result["fixture_path"]).read_text(encoding="utf-8"))
    point = output_fixture["cases"][0]["gold_scoring_points"][0]
    label = output_fixture["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"][0]
    assert point["required_terms_v1_5"] == ["生活区", "办公区", "材料加工和存放区"]
    assert label["hit"] == "hit"
    assert label["verifiable"] is True


def test_build_no_human_v1_5_list_rule_denominator_uses_true_official_terms(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text("{}", encoding="utf-8")
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q11",
                "official_answer": (
                    "①生活区；②办公区；③材料加工和存放区；"
                    "④防疫物资包括体温计、口罩、消毒剂；"
                    "⑤重点场所包括食堂、盥洗室、厕所。"
                ),
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "施工现场封闭管理'四区'除施工区外的另外三区,必须写出规范术语:生活区、办公区、材料加工和存放区(三项列举)",
                        "max_score": 3,
                    },
                    {
                        "point_id": "P2",
                        "label": "疫情防控物资,必须写出规范术语:体温计、口罩、消毒剂(三项列举)",
                        "max_score": 1.5,
                    },
                    {
                        "point_id": "P3",
                        "label": "定期消毒重点场所,必须写出规范术语:食堂、盥洗室、厕所(三项列举)",
                        "max_score": 1.5,
                    },
                ],
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "answer_text": "生活区、办公区、材料加工和存放区；体温计、口罩、消毒剂；食堂、盥洗室、厕所。",
                    }
                ],
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

    result = build_no_human_v1_5_bundle(
        fixture_path=fixture_path,
        source_root=source_root,
        output_fixture_path=tmp_path / "golden_no_human.json",
        output_dir=tmp_path / "artifacts",
        prior_report_path=None,
    )

    output_fixture = json.loads(Path(result["fixture_path"]).read_text(encoding="utf-8"))
    points = {point["point_id"]: point for point in output_fixture["cases"][0]["gold_scoring_points"]}
    labels = {
        label["point_id"]: label
        for label in output_fixture["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"]
    }
    assert points["P1"]["required_terms_v1_5"] == ["生活区", "办公区", "材料加工和存放区"]
    assert points["P2"]["required_terms_v1_5"] == ["体温计", "口罩", "消毒剂"]
    assert points["P3"]["required_terms_v1_5"] == ["食堂", "盥洗室", "厕所"]
    assert labels["P1"]["score"] == 3.0
    assert labels["P2"]["score"] == 1.5
    assert labels["P3"]["score"] == 1.5
    assert labels["P1"]["hit"] == labels["P2"]["hit"] == labels["P3"]["hit"] == "hit"


def test_build_no_human_v1_5_substring_context_risk_routes_to_class_b(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    (source_root / "2026教材").mkdir(parents=True)
    (source_root / "标准文件").mkdir(parents=True)
    (source_root / "2026教材" / "book.json").write_text("{}", encoding="utf-8")
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q11",
                "official_answer": "重点场所包括食堂、盥洗室、厕所。",
                "gold_scoring_points": [
                    {
                        "point_id": "P3",
                        "label": "定期消毒重点场所,必须写出规范术语:食堂、盥洗室、厕所(三项列举)",
                        "max_score": 1.5,
                    }
                ],
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "answer_text": "食堂和盥洗室要消毒，上厕所的地方也要管。",
                    }
                ],
            }
        ],
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")

    result = build_no_human_v1_5_bundle(
        fixture_path=fixture_path,
        source_root=source_root,
        output_fixture_path=tmp_path / "golden_no_human.json",
        output_dir=tmp_path / "artifacts",
        prior_report_path=None,
    )

    output_fixture = json.loads(Path(result["fixture_path"]).read_text(encoding="utf-8"))
    label = output_fixture["cases"][0]["eval_samples"][0]["no_human_v1_5_labels"][0]
    assert label["verifiable"] is False
    assert label["is_deterministic"] is False
    assert label["resolution_class"] == "B"
    assert label["residual_type"] == "boundary"
    assert label["context_risk_terms"] == ["厕所"]
