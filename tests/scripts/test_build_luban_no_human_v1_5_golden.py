from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_no_human_v1_5_golden import (
    _apply_provenance_adjudication,
    _normalized_text_contains,
    build_no_human_v1_5_bundle,
)


def test_build_no_human_v1_5_bundle_writes_auditable_fixture(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A000000_001",
                        "taxonomy": {"node_code": "1A000000"},
                        "content_markdown": "施工总进度计划表（图），资源需要量及供应平衡表。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
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


def test_build_no_human_v1_5_rejects_textbook_anchor_without_content_markdown_chunk(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "legacy_book.json").write_text(
        json.dumps({"content": "防护栏杆"}, ensure_ascii=False),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A436000",
                "official_answer": "防护栏杆。",
                "gold_scoring_points": [{"point_id": "P1", "label": "必须写出'防护栏杆'", "max_score": 1}],
                "eval_samples": [{"student_id": "S1", "answer_text": "防护栏杆"}],
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
    assert point["anchor_source"] == "official_answer_weak"
    assert point["chunk_id"] == ""
    assert label["verifiable"] is False
    assert label["resolution_class"] == "B"


def test_build_no_human_v1_5_rescues_mixed_textbook_and_weak_official_terms_per_term(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A436000_001",
                        "taxonomy": {"node_code": "1A436000"},
                        "content_markdown": "临边防护应设置防护栏杆。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A436000",
                "official_answer": "应写出官方弱项和防护栏杆。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出'官方弱项''防护栏杆'",
                        "max_score": 2,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "官方弱项，防护栏杆"}],
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
    assert point["anchor_source"] == "textbook"
    assert point["required_terms_v1_5"] == ["防护栏杆"]
    assert point["term_anchor_map"]["防护栏杆"]["anchor_source"] == "textbook"
    assert point["term_anchor_map"]["官方弱项"]["anchor_source"] == "official_answer_weak"
    assert label["verifiable"] is True
    assert label["is_deterministic"] is True
    assert label["resolution_class"] == "A"


def test_build_no_human_v1_5_strong_normalization_matches_r4_false_downgrades(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A433000_059_0089",
                        "taxonomy": {"node_code": "1A433000"},
                        "content_markdown": "资源需要量计划包括劳动力、预制构件、资金、测量和检验、机械设备等。",
                    },
                    {
                        "chunk_id": "1A434000_010",
                        "taxonomy": {"node_code": "1A434000"},
                        "content_markdown": "装配式结构施工时应检查锚固件及连接件。",
                    },
                    {
                        "chunk_id": "1A434020_001",
                        "taxonomy": {"node_code": "1A434020"},
                        "content_markdown": "施工现场封闭管理包括生活区、办公区、材料加工和存放区。",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q3",
                "question_node": "1A433000",
                "official_answer": "劳动力、预制构件、加工品、资金、测量、检验、机械设备、计量测量检验仪器。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出规范术语:劳动力、预制构件、加工品、资金、测量、检验、机械设备、计量测量检验仪器",
                        "max_score": 4,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "劳动力、预制构件、资金、测量检验、机械设备"}],
            },
            {
                "case_id": "Q9",
                "question_node": "1A434000",
                "official_answer": "锚固件。",
                "gold_scoring_points": [{"point_id": "P1", "label": "必须写出'锚固件'和官方弱项", "max_score": 2}],
                "eval_samples": [{"student_id": "S1", "answer_text": "锚固件"}],
            },
            {
                "case_id": "Q11",
                "question_node": "1A434020",
                "official_answer": "生活区；办公区。",
                "gold_scoring_points": [{"point_id": "P1", "label": "必须写出规范术语:生活区、办公区、官方弱项", "max_score": 3}],
                "eval_samples": [{"student_id": "S1", "answer_text": "生活区、办公区"}],
            },
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
    points = {
        (case["case_id"], point["point_id"]): point
        for case in output_fixture["cases"]
        for point in case["gold_scoring_points"]
    }
    assert points[("Q3", "P1")]["anchor_source"] == "textbook"
    assert points[("Q3", "P1")]["term_anchor_map"]["劳动力"]["anchor_source"] == "textbook"
    assert points[("Q3", "P1")]["term_anchor_map"]["机械设备"]["anchor_source"] == "textbook"
    assert points[("Q9", "P1")]["anchor_source"] == "textbook"
    assert points[("Q9", "P1")]["term_anchor_map"]["锚固件"]["anchor_source"] == "textbook"
    assert points[("Q11", "P1")]["anchor_source"] == "textbook"
    assert points[("Q11", "P1")]["term_anchor_map"]["生活区"]["anchor_source"] == "textbook"
    assert points[("Q11", "P1")]["term_anchor_map"]["办公区"]["anchor_source"] == "textbook"


def test_build_no_human_v1_5_normalized_text_contains_connector_and_punctuation_variants() -> None:
    assert _normalized_text_contains("计量、测量、检验仪器", "计量测量检验仪器")
    assert _normalized_text_contains("测量和检验", "测量检验")
    assert _normalized_text_contains("施工总进度计划表（图）", "施工总进度计划表(图)")
    assert _normalized_text_contains("① 劳动力", "劳动力")


def test_build_no_human_v1_5_r6_extracts_rubric_sentence_to_textbook_terms(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A413030_001",
                        "taxonomy": {"node_code": "1A413030"},
                        "content_markdown": "水泥砂浆防水层孔洞应采用M5防水砂浆修补。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q3-1A433000",
                "question_node": "1A433000",
                "official_answer": "应使用M5防水砂浆。",
                "gold_scoring_points": [
                    {
                        "point_id": "P6",
                        "label": "不妥③:必须写出'用M5普通砂浆堵孔抹平不妥,应使用M5防水砂浆'。关键词'防水砂浆'",
                        "max_score": 1,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "应使用M5防水砂浆。"}],
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
    assert point["anchor_source"] == "textbook"
    assert point["required_terms_v1_5"] == ["防水砂浆"]
    assert point["display_terms_v1_5"] == ["防水砂浆"]
    assert point["term_anchor_map"]["防水砂浆"]["chunk_id"] == "1A413030_001"
    assert point["term_anchor_map"]["防水砂浆"]["provenance_confidence"] == "needs_review"
    assert point["term_squeeze_v1_5"]["rubric_to_textbook_terms_r6"] is True


def test_build_no_human_v1_5_r6_rescues_multi_term_roof_defect_per_term(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A413030_002",
                        "taxonomy": {"node_code": "1A413030"},
                        "content_markdown": "找平层应留设分格缝，卷材搭接长度应符合规定。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q6-1A413000-罚则",
                "question_node": "1A413000",
                "official_answer": "找平层的分格缝设置不当、屋面板因温度变化产生胀缩、卷材搭接长度太小。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "(1) 找出原因分析中的不妥之处:②找平层的分格缝设置不当、④屋面板因温度变化产生胀缩、⑤卷材搭接长度太小",
                        "max_score": 3,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "分格缝设置不当，搭接长度太小。"}],
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
    assert point["anchor_source"] == "textbook"
    assert point["required_terms_v1_5"] == ["搭接长度", "分格缝"]
    assert point["term_anchor_map"]["搭接长度"]["anchor_source"] == "textbook"
    assert point["term_anchor_map"]["分格缝"]["anchor_source"] == "textbook"


def test_build_no_human_v1_5_r6_rescues_bazixing_without_loose_anchor(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A413030_003",
                        "taxonomy": {"node_code": "1A413030"},
                        "content_markdown": "绑扎时应注意相邻绑扎点的钢丝扣要成八字形。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q16-1A436000",
                "question_node": "1A436000",
                "official_answer": "方向应不同，丝扣呈八字形。",
                "gold_scoring_points": [
                    {
                        "point_id": "P4",
                        "label": "不妥3:绑扎点钢筋扣绑扎方向要求一致;理由必须写出'方向应不同,丝扣呈八字形(八字扣)'",
                        "max_score": 1,
                    }
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "丝扣呈八字形。"}],
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
    assert point["anchor_source"] == "textbook"
    assert point["required_terms_v1_5"] == ["八字形"]
    assert point["term_anchor_map"]["八字形"]["anchor_source"] == "textbook"


def test_build_no_human_v1_5_r6_marks_targeted_compression_steps_as_calculation(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps({"content_blocks": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q3-1A433000",
                "question_node": "1A433000",
                "official_answer": "先压缩主体结构2天，再压缩室内装修3天。",
                "gold_scoring_points": [
                    {"point_id": "P2", "label": "压缩顺序-第一步:必须写出'先压缩主体结构2天'", "max_score": 1},
                    {"point_id": "P3", "label": "压缩顺序-第二步:必须写出'再压缩室内装修3天'", "max_score": 1},
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "先压缩主体结构2天，再压缩室内装修3天。"}],
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
    assert points["P2"]["point_type"] == "calculation"
    assert points["P2"]["anchor_source"] == "calculation"
    assert points["P2"]["calculation_expected_terms_v1_5"] == ["主体结构2天"]
    assert points["P3"]["calculation_expected_terms_v1_5"] == ["室内装修3天"]


def test_build_no_human_v1_5_r6_does_not_rescue_non_target_weak_point(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A434000_001",
                        "taxonomy": {"node_code": "1A434000"},
                        "content_markdown": "施工现场需要合理布置。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A434000",
                "official_answer": "体温计、口罩、消毒剂。",
                "gold_scoring_points": [
                    {"point_id": "P2", "label": "疫情防控物资,必须写出规范术语:体温计、口罩、消毒剂", "max_score": 1.5}
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "体温计、口罩、消毒剂。"}],
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
    assert point["anchor_source"] == "official_answer_weak"
    assert label["verifiable"] is False


def test_build_no_human_v1_5_expands_short_common_single_term_to_distinctive_phrase(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A436000_001",
                        "taxonomy": {"node_code": "1A436000"},
                        "content_markdown": "临边作业应设置防护栏杆。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A436000",
                "official_answer": "应设置防护栏杆。",
                "gold_scoring_points": [{"point_id": "P1", "label": "必须写出'防护'，本点指防护栏杆", "max_score": 1}],
                "eval_samples": [{"student_id": "S1", "answer_text": "应设置防护栏杆。"}],
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
    assert point["required_terms_v1_5"] == ["防护栏杆"]
    assert len(point["required_terms_v1_5"][0]) > 3
    assert point["anchor_source"] == "textbook"
    assert label["hit"] == "hit"


def test_build_no_human_v1_5_recovers_label_terms_from_official_answer_after_junk_raw_terms(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A434020_001",
                        "taxonomy": {"node_code": "1A434020"},
                        "content_markdown": "施工现场封闭管理包括生活区、办公区、材料加工和存放区。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A434020_001",
                        "taxonomy": {"node_code": "1A434020"},
                        "content_markdown": "生活区、办公区、材料加工和存放区。防疫物资包括体温计、口罩、消毒剂。重点场所包括食堂、盥洗室、厕所。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A434020_001",
                        "taxonomy": {"node_code": "1A434020"},
                        "content_markdown": "重点场所包括食堂、盥洗室、厕所。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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


def test_build_no_human_v1_5_marks_official_only_terms_as_weak_not_deterministic(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps(
            {
                "content_blocks": [
                    {
                        "chunk_id": "1A434000_001_0001",
                        "taxonomy": {"node_code": "1A434000"},
                        "source_meta": {"page_num": 1},
                        "content_markdown": "教材没有这些采分术语。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "Q11",
                "question_node": "1A434000",
                "official_answer": "①生活区；②办公区；③材料加工和存放区。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "必须写出规范术语:生活区、办公区、材料加工和存放区(三项列举)",
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
    assert point["anchor_source"] == "official_answer_weak"
    assert point["point_type"] == "text_term"
    assert label["verifiable"] is False
    assert label["resolution_class"] == "B"


def test_build_no_human_v1_5_marks_calculation_and_figure_points_outside_textbook_coverage(tmp_path) -> None:
    source_root = tmp_path / "docs2026"
    textbook_dir = source_root / "2026教材" / "第二次加强"
    textbook_dir.mkdir(parents=True)
    (textbook_dir / "FINAL_CLEANED_BOOK2026-222-382_fixed.json").write_text(
        json.dumps({"content_blocks": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    fixture = {
        "suite": "luban_case_grading_golden_v1",
        "cases": [
            {
                "case_id": "QX",
                "question_node": "1A413000",
                "official_answer": "施工配合比中砂用量为707.2kg。图中①为塔吊。",
                "gold_scoring_points": [
                    {
                        "point_id": "P1",
                        "label": "施工配合比 中砂用量 = 707.2kg",
                        "max_score": 1,
                    },
                    {
                        "point_id": "P1b",
                        "label": "主体施工阶段劳动力计算:57600×8/(2×7×120)=274.3,取整275名",
                        "max_score": 1,
                    },
                    {
                        "point_id": "P2",
                        "label": "图中①编号设施名称定位: ①塔吊（图中须含起重机均为junk）",
                        "max_score": 1,
                    },
                ],
                "eval_samples": [{"student_id": "S1", "answer_text": "中砂707.2kg，劳动力取整275名，①塔吊。"}],
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
    assert points["P1"]["point_type"] == "calculation"
    assert points["P1"]["anchor_source"] == "calculation"
    assert points["P1"]["required_terms_v1_5"] == []
    assert points["P1"]["calculation_expected_terms_v1_5"] == ["707.2kg"]
    assert labels["P1"]["hit"] == "hit"
    assert labels["P1"]["is_deterministic"] is True
    assert points["P1b"]["calculation_expected_terms_v1_5"] == ["275名"]
    assert labels["P1b"]["hit"] == "hit"
    assert points["P2"]["point_type"] == "figure_label"
    assert points["P2"]["anchor_source"] == "exam_figure"
    assert points["P2"]["required_terms_v1_5"] == ["塔吊"]
    assert labels["P2"]["hit"] == "hit"


def test_provenance_adjudication_downgrades_mis_provenance_term_but_keeps_in_context_term() -> None:
    # r7: 资金 is 张冠李戴 (matched in 开工条件 chunk, not the 资源需求计划 passage);
    # 劳动力 is a genuine in-chapter textbook term. Downgrading 资金 must not kill the point.
    source = {
        "anchor_source": "textbook",
        "chunk_id": "1A421000_003_0003",
        "textbook_quote": "资金",
        "term_anchor_map": {
            "资金": {"anchor_source": "textbook", "chunk_id": "1A421000_003_0003", "node_code": "1A421000", "verified": True},
            "劳动力": {"anchor_source": "textbook", "chunk_id": "1A433000_059_0089", "node_code": "1A433000", "verified": True},
        },
    }
    adjudication = {("Q3-1A433000", "P1", "资金"): {"decision": "downgrade"}}
    result = _apply_provenance_adjudication(
        source, case_id="Q3-1A433000", point_id="P1", case_node="1A433000", corpus=[], adjudication=adjudication
    )
    assert result["term_anchor_map"]["资金"]["anchor_source"] == "official_answer_weak"
    assert result["term_anchor_map"]["资金"]["verified"] is False
    assert result["term_anchor_map"]["劳动力"]["anchor_source"] == "textbook"
    assert result["anchor_source"] == "textbook"  # 劳动力 survives → point stays textbook
    assert result["chunk_id"] == "1A433000_059_0089"  # point chunk re-points to surviving textbook term


def test_provenance_adjudication_downgrades_whole_point_when_only_term_is_mis_provenance() -> None:
    source = {
        "anchor_source": "textbook",
        "chunk_id": "1A422000_053_0079",
        "textbook_quote": "塔吊",
        "term_anchor_map": {
            "塔吊": {"anchor_source": "textbook", "chunk_id": "1A422000_053_0079", "node_code": "1A422000", "verified": True},
        },
    }
    adjudication = {("Q7-1A431000", "P1", "塔吊"): {"decision": "downgrade"}}
    result = _apply_provenance_adjudication(
        source, case_id="Q7-1A431000", point_id="P1", case_node="1A431000", corpus=[], adjudication=adjudication
    )
    assert result["term_anchor_map"]["塔吊"]["anchor_source"] == "official_answer_weak"
    assert result["anchor_source"] == "official_answer_weak"  # no textbook term survives


def test_provenance_adjudication_reanchors_term_to_authoritative_chunk() -> None:
    # 汽油 matched a 涂装溶剂 chunk (coincidental); its real home is the carbon-energy passage.
    energy_chunk = {
        "source_class": "textbook",
        "chunk_id": "1A422000_055_0081",
        "node_code": "1A422000",
        "text": "建造阶段碳排放的关键在于确定施工阶段的电、汽油、柴油、燃气等能源的消耗量。",
        "content_hash": "h",
        "source_path": "x.json",
        "json_pointer": "$.content_blocks[0].content_markdown",
    }
    source = {
        "anchor_source": "official_answer_weak",
        "chunk_id": "",
        "textbook_quote": "汽油",
        "term_anchor_map": {
            "汽油": {"anchor_source": "official_answer_weak", "chunk_id": "", "node_code": "1A422000", "verified": False},
        },
    }
    adjudication = {("Q14-1A430000", "P5", "汽油"): {"decision": "reanchor", "chunk_id": "1A422000_055_0081"}}
    result = _apply_provenance_adjudication(
        source, case_id="Q14-1A430000", point_id="P5", case_node="1A430000", corpus=[energy_chunk], adjudication=adjudication
    )
    entry = result["term_anchor_map"]["汽油"]
    assert entry["anchor_source"] == "textbook"
    assert entry["chunk_id"] == "1A422000_055_0081"
    assert entry["verified"] is True
    assert result["anchor_source"] == "textbook"


def test_provenance_adjudication_flags_unadjudicated_cross_node_anchor_as_needs_review() -> None:
    source = {
        "anchor_source": "textbook",
        "chunk_id": "1A422000_022_0031",
        "textbook_quote": "甲醛",
        "term_anchor_map": {
            "甲醛": {"anchor_source": "textbook", "chunk_id": "1A422000_022_0031", "node_code": "1A422000", "verified": True},
            "进度表": {"anchor_source": "textbook", "chunk_id": "1A433000_059_0089", "node_code": "1A433000", "verified": True},
        },
    }
    result = _apply_provenance_adjudication(
        source, case_id="Q3-1A433000", point_id="P10", case_node="1A433000", corpus=[], adjudication={}
    )
    assert result["term_anchor_map"]["甲醛"]["provenance_confidence"] == "needs_review"  # cross-node, unadjudicated
    assert result["term_anchor_map"]["进度表"]["provenance_confidence"] == "high"  # same node family
