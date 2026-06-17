from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _patch_batch() -> dict:
    return {
        "schema": "luban_rich_leaf_candidate_patch_batch.v1",
        "candidate_patches": [
            {
                "patch_id": "patch_good",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "name_path": "建筑设计程序与要求 > 建筑设计程序",
                "missing_lane": "textbook",
                "candidate_only": True,
                "review_status": "pending_review",
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "source_ref_candidate": {
                    "source_ref_id": "SRC1",
                    "source_lane": "textbook",
                    "path": "教材原文/source.json",
                    "record_id": "TB1",
                    "span": "建筑设计程序一般包括方案设计、初步设计、施工图设计等阶段。",
                    "span_hash": "hash1",
                    "matched_terms": ["建筑设计程序", "初步设计", "施工图设计"],
                    "retrieval_score": 3.5,
                    "provenance": {"page": 12},
                },
                "review_packet": {
                    "snippet": "建筑设计程序一般包括方案设计、初步设计、施工图设计等阶段。",
                    "query_context": {
                        "question_source_record_ids": ["Q1"],
                        "question_source_spans": ["工程概算书属于初步设计文件内容。"],
                        "question_source_only_not_support": True,
                    },
                },
            },
            {
                "patch_id": "patch_rejected",
                "artifact_id": "A2",
                "leaf_id": "L2",
                "name_path": "错源",
                "missing_lane": "lecture",
                "candidate_only": True,
                "review_status": "pending_review",
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "source_ref_candidate": {
                    "source_ref_id": "SRC2",
                    "source_lane": "lecture",
                    "path": "讲义/地下连续墙.md",
                    "record_id": "LEC_BAD",
                    "span": "A. 墙体刚度大 B. 抗渗性能好",
                    "span_hash": "hash2",
                    "matched_terms": ["A.", "B."],
                },
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


def _patch_audit() -> dict:
    return {
        "schema": "luban_rich_leaf_patch_evidence_audit.v1",
        "patch_audits": [
            {
                "patch_id": "patch_good",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "missing_lane": "textbook",
                "audit_decision": "machine_precheck_pass",
                "review_status": "machine_precheck_only",
                "reason_codes": [],
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "candidate_only": True,
            },
            {
                "patch_id": "patch_rejected",
                "artifact_id": "A2",
                "leaf_id": "L2",
                "missing_lane": "lecture",
                "audit_decision": "machine_reject",
                "review_status": "machine_precheck_only",
                "reason_codes": ["option_marker_only_match"],
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "candidate_only": True,
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


def test_semantic_audit_packets_include_only_machine_pass_patches_and_review_contract() -> None:
    from scripts.run_luban_rich_leaf_semantic_audit_packets import build_semantic_audit_packet_report

    report = build_semantic_audit_packet_report(patch_batch=_patch_batch(), patch_audit_report=_patch_audit())

    assert report["schema"] == "luban_rich_leaf_semantic_audit_packets.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "semantic_verdict_recorded": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {
        "input_patch_count": 2,
        "machine_precheck_pass_count": 1,
        "packet_count": 1,
        "skipped_non_pass_count": 1,
    }
    assert all(value in (False, 0) for value in report["safety"].values())

    packet = report["semantic_audit_packets"][0]
    assert packet["patch_id"] == "patch_good"
    assert packet["leaf_id"] == "L1"
    assert packet["review_status"] == "semantic_review_pending"
    assert packet["allowed_decisions"] == [
        "accept_source_ref_candidate",
        "reject_wrong_leaf_source",
        "needs_external_source",
        "needs_leaf_split_or_retaxonomy",
    ]
    assert packet["apply_allowed"] is False
    assert packet["runtime_install_allowed"] is False
    assert packet["source_ref_candidate"]["span"]
    assert packet["review_questions"]
    assert packet["machine_precheck"]["audit_decision"] == "machine_precheck_pass"
    assert "question_source_spans" in packet["query_context"]


def test_cli_writes_semantic_audit_packets(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_audit_packets import main

    patch_path = tmp_path / "candidate_patches.json"
    audit_path = tmp_path / "patch_evidence_audit.json"
    output_dir = tmp_path / "out"
    _write_json(patch_path, _patch_batch())
    _write_json(audit_path, _patch_audit())

    exit_code = main(
        [
            "--patches",
            str(patch_path),
            "--patch-audit",
            str(audit_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "semantic_audit_packets.json").read_text("utf-8"))
    assert report["summary"]["packet_count"] == 1
    assert report["semantic_audit_packets"][0]["patch_id"] == "patch_good"
