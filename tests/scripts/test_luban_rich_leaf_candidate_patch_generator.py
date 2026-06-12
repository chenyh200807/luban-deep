from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _source_gap_report() -> dict:
    return {
        "schema": "luban_rich_leaf_source_gap_candidates.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "rag_or_chunk_retrieval_is_not_authority": True,
            "question_source_is_query_context_only": True,
        },
        "summary": {"source_record_count": 3},
        "source_gap_candidates": [
            {
                "leaf_id": "L1",
                "artifact_id": "rich_leaf_skeleton_L1",
                "name_path": "建筑设计程序",
                "missing_lane": "textbook",
                "status": "strong_candidate_sources_found",
                "strong_candidate_threshold": 2.0,
                "query_context": {
                    "question_source_record_ids": ["Q1"],
                    "question_source_only_not_support": True,
                },
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "2026教材原文/建筑设计.json",
                        "record_id": "TB1",
                        "provenance": {"page": 12},
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "snippet": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "hash": "retrieval-hash",
                        "matched_terms": ["方案设计", "初步设计", "施工图设计"],
                        "score": 3.5,
                        "retrieval_stage": "local_corpus_record",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
            {
                "leaf_id": "L2",
                "artifact_id": "rich_leaf_skeleton_L2",
                "name_path": "工程预付款与起扣点",
                "missing_lane": "standard",
                "status": "weak_candidate_sources_found",
                "strong_candidate_threshold": 2.0,
                "query_context": {},
                "candidates": [
                    {
                        "source_lane": "standard",
                        "source_path": "规范原文/合同.json",
                        "record_id": "STD1",
                        "span": "工程预付款起扣点计算。",
                        "snippet": "工程预付款起扣点计算。",
                        "hash": "weak-hash",
                        "matched_terms": ["工程预付款"],
                        "score": 1.2,
                        "retrieval_stage": "local_corpus_record",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
            {
                "leaf_id": "L3",
                "artifact_id": "rich_leaf_skeleton_L3",
                "name_path": "污染候选",
                "missing_lane": "lecture",
                "status": "strong_candidate_sources_found",
                "strong_candidate_threshold": 2.0,
                "query_context": {},
                "candidates": [
                    {
                        "source_lane": "question",
                        "source_path": "真题及答案解析/FINAL_CLEANED_EXAM.json",
                        "record_id": "Q_BAD",
                        "span": "答案解析内容。",
                        "snippet": "答案解析内容。",
                        "hash": "bad-hash",
                        "matched_terms": ["答案解析"],
                        "score": 5.0,
                        "retrieval_stage": "local_corpus_record",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
            {
                "leaf_id": "L4",
                "artifact_id": "rich_leaf_skeleton_L4",
                "name_path": "隐形污染候选",
                "missing_lane": "textbook",
                "status": "strong_candidate_sources_found",
                "strong_candidate_threshold": 2.0,
                "query_context": {},
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "unclassified/source.json",
                        "record_id": "PRACTICE_AS_TEXTBOOK",
                        "provenance": {"source": "ZL864考证宝典必刷500题2025"},
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "snippet": "必刷500题：建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "hash": "hidden-bad-hash",
                        "matched_terms": ["方案设计", "初步设计"],
                        "score": 4.0,
                        "retrieval_stage": "source_bundle",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
            {
                "leaf_id": "L5",
                "artifact_id": "rich_leaf_skeleton_L5",
                "name_path": "英文污染候选",
                "missing_lane": "textbook",
                "status": "strong_candidate_sources_found",
                "strong_candidate_threshold": 2.0,
                "query_context": {},
                "candidates": [
                    {
                        "source_lane": "textbook",
                        "source_path": "unclassified/source.json",
                        "record_id": "MCQ_AS_TEXTBOOK",
                        "provenance": {"source": "ZL864 MCQ Import practice book"},
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "snippet": "MCQ Import practice book: 建筑设计程序。",
                        "hash": "english-hidden-bad-hash",
                        "matched_terms": ["方案设计", "初步设计"],
                        "score": 4.0,
                        "retrieval_stage": "source_bundle",
                        "candidate_only": True,
                        "install_allowed": False,
                    }
                ],
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_build_candidate_patches_only_promotes_strong_clean_candidates() -> None:
    from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash
    from scripts.run_luban_rich_leaf_candidate_patch_generator import build_candidate_patch_batch

    batch = build_candidate_patch_batch(source_gap_report=_source_gap_report(), bundle_version="v_patch_demo")

    assert batch["schema"] == "luban_rich_leaf_candidate_patch_batch.v1"
    assert batch["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "patches_apply_allowed": False,
        "runtime_install_allowed": False,
    }
    assert batch["summary"]["patch_count"] == 1
    assert batch["summary"]["skipped_non_strong_count"] == 1
    assert batch["summary"]["skipped_suspicious_count"] == 3
    assert all(value in (False, 0) for value in batch["safety"].values())

    patch = batch["candidate_patches"][0]
    assert patch["operation"] == "add_source_ref_candidate"
    assert patch["candidate_only"] is True
    assert patch["review_status"] == "pending_review"
    assert patch["apply_allowed"] is False
    assert patch["runtime_install_allowed"] is False
    assert patch["source_ref_candidate"]["source_lane"] == "textbook"
    assert patch["source_ref_candidate"]["span_hash"] == source_span_hash(
        "建筑设计程序包括方案设计、初步设计和施工图设计。"
    )
    assert patch["source_ref_candidate"]["retrieval_hash"] == "retrieval-hash"
    assert patch["review_packet"]["question_source_only_not_support"] is True


def test_cli_writes_candidate_patch_batch(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_candidate_patch_generator import main

    source_gap_path = tmp_path / "source_gap_candidates.json"
    output_dir = tmp_path / "out"
    _write_json(source_gap_path, _source_gap_report())

    exit_code = main(
        [
            "--source-gap-candidates",
            str(source_gap_path),
            "--bundle-version",
            "v_patch_cli",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "candidate_patches.json").read_text("utf-8"))
    assert report["bundle_version"] == "v_patch_cli"
    assert report["summary"]["patch_count"] == 1
    assert report["candidate_patches"][0]["source_ref_candidate"]["source_dataset_id"] == "textbook"
