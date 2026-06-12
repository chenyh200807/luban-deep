from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _skeleton_batch() -> dict:
    return {
        "schema": "luban_rich_leaf_skeleton_batch.v1",
        "bundle_version": "v_rich_leaf_skeleton_candidate_20260611",
        "rich_leaf_artifacts": [
            {
                "artifact_id": "rich_leaf_skeleton_L1",
                "leaf_id": "L1",
                "name_path": "建筑工程技术 > 建筑设计 > 建筑设计程序",
                "missing_source_lanes": ["textbook", "standard", "lecture"],
                "source_refs": [
                    {
                        "source_lane": "question",
                        "record_id": "Q1",
                        "span": "工程概算书属于初步设计文件内容。",
                    }
                ],
                "teaching_cards": [
                    {
                        "card": "建筑设计程序 | keywords: 方案设计, 初步设计, 施工图设计",
                        "claim_status": "candidate_only",
                    }
                ],
            },
            {
                "artifact_id": "rich_leaf_skeleton_L2",
                "leaf_id": "L2",
                "name_path": "主体结构工程施工 > 钢结构安装方法 > 滑移法适用范围",
                "missing_source_lanes": ["lecture"],
                "source_refs": [],
                "teaching_cards": [
                    {
                        "card": "滑移法适用范围 | keywords: 平行滑轨, 跨越施工, 场地狭窄",
                        "claim_status": "candidate_only",
                    }
                ],
            },
            {
                "artifact_id": "rich_leaf_skeleton_L3",
                "leaf_id": "L3",
                "name_path": "智能建造新技术 > 工程预付款与起扣点",
                "missing_source_lanes": ["standard"],
                "source_refs": [],
                "teaching_cards": [
                    {
                        "card": "工程预付款与起扣点 | keywords: 预付款比例, 主要材料占比, 起扣点计算",
                        "claim_status": "candidate_only",
                    }
                ],
            },
        ],
    }


def _sample_manifest() -> dict:
    return {
        "schema": "luban_rich_leaf_phase1_sample_manifest.v1",
        "input_hashes": {"canonical_unified_knowledge": "hash-unified"},
        "selected_leaves": [
            {
                "leaf_id": "L1",
                "keywords": ["方案设计", "初步设计", "施工图设计"],
                "name_path": "建筑工程技术 > 建筑设计 > 建筑设计程序",
            },
            {
                "leaf_id": "L2",
                "keywords": ["平行滑轨", "跨越施工", "场地狭窄"],
                "name_path": "主体结构工程施工 > 钢结构安装方法 > 滑移法适用范围",
            },
            {
                "leaf_id": "L3",
                "keywords": ["预付款比例", "主要材料占比", "起扣点计算"],
                "name_path": "智能建造新技术 > 工程预付款与起扣点",
            },
        ],
    }


def test_build_source_gap_candidates_respects_missing_lanes_and_question_context() -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import (
        SourceRecord,
        build_source_gap_candidates,
    )

    source_records = [
        SourceRecord(
            source_lane="textbook",
            source_path="2026教材/建筑设计.json",
            record_id="TB1",
            text="建筑设计程序包括方案设计、初步设计和施工图设计等阶段。",
            provenance={"page": 12},
        ),
        SourceRecord(
            source_lane="question",
            source_path="题库/近三年真题.json",
            record_id="Q1",
            text="工程概算书属于初步设计文件内容。",
            provenance={"year": 2024},
        ),
        SourceRecord(
            source_lane="lecture",
            source_path="讲义/钢结构/page.json",
            record_id="LEC1",
            text="滑移法可用于场地狭窄、起重运输不便且可设置平行滑轨的跨越施工。",
            provenance={"lecture": "demo"},
        ),
    ]

    report = build_source_gap_candidates(
        skeleton_batch=_skeleton_batch(),
        sample_manifest=_sample_manifest(),
        source_records=source_records,
        strong_candidate_threshold=2.0,
    )

    assert report["schema"] == "luban_rich_leaf_source_gap_candidates.v1"
    assert report["summary"]["gap_lane_count"] == 5
    assert report["summary"]["strong_candidate_sources_found"] == 2
    assert report["summary"]["weak_candidate_sources_found"] == 0
    assert report["summary"]["no_candidate_sources_found"] == 3
    assert all(value in (False, 0) for value in report["safety"].values())

    l1_textbook = next(
        row
        for row in report["source_gap_candidates"]
        if row["leaf_id"] == "L1" and row["missing_lane"] == "textbook"
    )
    assert l1_textbook["status"] == "strong_candidate_sources_found"
    assert l1_textbook["query_context"]["question_source_record_ids"] == ["Q1"]
    assert l1_textbook["candidates"][0]["source_lane"] == "textbook"
    assert l1_textbook["candidates"][0]["candidate_only"] is True
    assert l1_textbook["candidates"][0]["install_allowed"] is False
    assert l1_textbook["candidates"][0]["span"]
    assert l1_textbook["candidates"][0]["snippet"]
    assert l1_textbook["candidates"][0]["hash"]
    assert "初步设计" in l1_textbook["candidates"][0]["matched_terms"]

    l1_missing_support_lanes = [
        candidate["source_lane"]
        for row in report["source_gap_candidates"]
        if row["leaf_id"] == "L1"
        for candidate in row["candidates"]
    ]
    assert "question" not in l1_missing_support_lanes

    l2_lecture = next(row for row in report["source_gap_candidates"] if row["leaf_id"] == "L2")
    assert l2_lecture["status"] == "strong_candidate_sources_found"
    assert l2_lecture["candidates"][0]["source_path"] == "讲义/钢结构/page.json"

    l3_standard = next(row for row in report["source_gap_candidates"] if row["leaf_id"] == "L3")
    assert l3_standard["status"] == "no_candidate_sources_found"
    assert l3_standard["candidates"] == []


def test_source_gap_ignores_question_option_markers_when_scoring_support_candidates() -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import (
        SourceRecord,
        build_source_gap_candidates,
    )

    skeleton_batch = {
        "schema": "luban_rich_leaf_skeleton_batch.v1",
        "rich_leaf_artifacts": [
            {
                "artifact_id": "rich_leaf_skeleton_L_OPTION",
                "leaf_id": "L_OPTION",
                "name_path": "建筑设计程序与要求 > 建筑设计程序",
                "missing_source_lanes": ["lecture"],
                "source_refs": [
                    {
                        "source_lane": "question",
                        "record_id": "Q_OPTION",
                        "span": "工程概算书属于（ ）。\nA. 方案设计\nB. 初步设计\nC. 施工图设计\nD. 专项设计",
                    }
                ],
                "teaching_cards": [
                    {
                        "card": "建筑设计程序 | keywords: 方案设计, 初步设计, 施工图设计",
                        "claim_status": "candidate_only",
                    }
                ],
            }
        ],
    }
    source_records = [
        SourceRecord(
            source_lane="lecture",
            source_path="讲义/地下连续墙.md",
            record_id="LEC_BAD_OPTION",
            text="地下连续墙施工特点包括：A. 墙体刚度大 B. 抗渗性能好 C. 两墙合一 D. 噪音低。",
            provenance={"topic": "地下连续墙施工技术"},
        )
    ]

    report = build_source_gap_candidates(
        skeleton_batch=skeleton_batch,
        sample_manifest={"selected_leaves": []},
        source_records=source_records,
        strong_candidate_threshold=2.0,
    )

    row = report["source_gap_candidates"][0]
    assert row["status"] == "no_candidate_sources_found"
    assert "A." not in row["terms"]
    assert "B." not in row["terms"]
    assert row["candidates"] == []


def test_cli_writes_review_only_source_gap_candidates(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import main

    skeleton_path = tmp_path / "rich_leaf_skeleton_candidates.json"
    sample_path = tmp_path / "sample_manifest.json"
    source_bundle_path = tmp_path / "source_bundle.json"
    output_dir = tmp_path / "out"

    _write_json(skeleton_path, _skeleton_batch())
    _write_json(sample_path, _sample_manifest())
    _write_json(
        source_bundle_path,
        {
            "schema": "source_corpus_candidates.v1",
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "2026教材/建筑设计.json",
                    "record_id": "TB1",
                    "text": "建筑设计程序包括方案设计、初步设计和施工图设计等阶段。",
                    "provenance": {"page": 12},
                },
                {
                    "source_lane": "question",
                    "source_path": "题库/近三年真题.json",
                    "record_id": "Q1",
                    "text": "工程概算书属于初步设计文件内容。",
                    "provenance": {"year": 2024},
                },
                {
                    "source_lane": "standard",
                    "source_path": "题库/标准答案解析.json",
                    "record_id": "BAD_STANDARD_ANSWER",
                    "text": "工程预付款与起扣点计算：预付款比例、主要材料占比、起扣点计算。",
                    "provenance": {"source": "standard answer analysis"},
                },
            ],
        },
    )

    exit_code = main(
        [
            "--skeleton-batch",
            str(skeleton_path),
            "--sample-manifest",
            str(sample_path),
            "--source-bundle",
            str(source_bundle_path),
            "--unified-bundle",
            str(tmp_path / "missing_unified.json"),
            "--source-root",
            str(tmp_path / "missing_source_root"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "source_gap_candidates.json").read_text("utf-8"))
    assert report["summary"]["candidate_total"] == 1
    assert report["summary"]["question_sources_used_as_query_context"] == 1
    assert all(
        candidate["record_id"] != "BAD_STANDARD_ANSWER"
        for row in report["source_gap_candidates"]
        for candidate in row["candidates"]
    )
    assert report["source_gap_candidates"][0]["candidates"][0]["candidate_only"] is True
    assert report["source_gap_candidates"][0]["candidates"][0]["install_allowed"] is False
    assert report["source_gap_candidates"][0]["candidates"][0]["source_path"] == "2026教材/建筑设计.json"
    assert report["source_gap_candidates"][0]["candidates"][0]["record_id"] == "TB1"
    assert report["source_gap_candidates"][0]["candidates"][0]["span"]
    assert report["source_gap_candidates"][0]["candidates"][0]["hash"]
    assert report["safety"] == {
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "installed_runtime_supply": False,
        "production_write_count": 0,
        "release_truth_claimed": False,
    }


def test_source_bundle_downgrades_practice_shape_before_trusting_explicit_lane() -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_source_bundle

    records = load_source_records_from_source_bundle(
        {
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "unclassified/source.json",
                    "record_id": "PRACTICE_AS_TEXTBOOK",
                    "content_type": "exercise",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    "question_data": {"stem": "下列说法正确的是？"},
                    "correct_answer": "A",
                    "provenance": {"source": "ZL864考证宝典必刷500题2025"},
                }
            ]
        }
    )

    assert len(records) == 1
    assert records[0].source_lane == "question"


def test_source_bundle_downgrades_english_practice_provenance_before_trusting_explicit_lane() -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_source_bundle

    records = load_source_records_from_source_bundle(
        {
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "unclassified/source.json",
                    "record_id": "MCQ_AS_TEXTBOOK",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    "provenance": {"source": "ZL864 MCQ Import practice book"},
                }
            ]
        }
    )

    assert len(records) == 1
    assert records[0].source_lane == "question"


def test_source_bundle_downgrades_practice_source_meta_before_trusting_explicit_lane() -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_source_bundle

    records = load_source_records_from_source_bundle(
        {
            "source_records": [
                {
                    "source_lane": "textbook",
                    "source_path": "unclassified/source.json",
                    "record_id": "SOURCE_META_AS_TEXTBOOK",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    "source_meta": {"source": "ZL864考证宝典必刷500题2025"},
                }
            ]
        }
    )

    assert len(records) == 1
    assert records[0].source_lane == "question"


def test_source_root_does_not_treat_parent_question_bank_as_lane_authority(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_root

    source_root = tmp_path / "题库"
    textbook_path = source_root / "2026教材原文" / "建筑设计.json"
    _write_json(
        textbook_path,
        {
            "chunks": [
                {
                    "chunk_id": "TB1",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                }
            ]
        },
    )
    answer_path = source_root / "2023年一级建造师《建筑实务》考试真题及答案解析" / "answers.json"
    _write_json(
        answer_path,
        {
            "chunks": [
                {
                    "chunk_id": "Q1",
                    "content_markdown": "工程概算书属于初步设计文件内容。",
                }
            ]
        },
    )

    records = load_source_records_from_root(source_root)

    textbook = next(record for record in records if record.record_id == "TB1")
    answer = next(record for record in records if record.record_id == "Q1")
    assert textbook.source_lane == "textbook"
    assert "2026教材原文" in textbook.source_path
    assert answer.source_lane == "question"


def test_source_root_downgrades_practice_books_even_when_metadata_says_textbook(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_root

    source_root = tmp_path / "题库"
    practice_book = source_root / "864考证宝典ZL" / "FINAL_CLEANED_ZL500.json"
    _write_json(
        practice_book,
        {
            "meta": {"source_type": "TEXTBOOK"},
            "chunks": [
                {
                    "chunk_id": "ZL1",
                    "content_type": "exercise",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                }
            ],
        },
    )

    records = load_source_records_from_root(source_root)

    assert len(records) == 1
    assert records[0].record_id == "ZL1"
    assert records[0].source_lane == "question"


def test_source_root_uses_json_file_metadata_for_non_exercise_source_text(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_root

    source_root = tmp_path / "题库"
    textbook = source_root / "未分类资料" / "building-design.json"
    _write_json(
        textbook,
        {
            "meta": {"source_type": "TEXTBOOK"},
            "chunks": [
                {
                    "chunk_id": "TB1",
                    "content_type": "source_clause",
                    "content_markdown": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                }
            ],
        },
    )

    records = load_source_records_from_root(source_root)

    assert len(records) == 1
    assert records[0].record_id == "TB1"
    assert records[0].source_lane == "textbook"
