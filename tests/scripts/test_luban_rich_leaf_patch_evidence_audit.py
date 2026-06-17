from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _patch(
    *,
    patch_id: str,
    name_path: str,
    span: str,
    matched_terms: list[str],
    span_hash: str | None = None,
    source_lane: str = "textbook",
    missing_lane: str = "textbook",
    path: str = "教材原文/source.json",
    provenance: dict | None = None,
) -> dict:
    return {
        "patch_id": patch_id,
        "operation": "add_source_ref_candidate",
        "artifact_id": f"artifact_{patch_id}",
        "leaf_id": f"leaf_{patch_id}",
        "name_path": name_path,
        "missing_lane": missing_lane,
        "candidate_only": True,
        "review_status": "pending_review",
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "source_ref_candidate": {
            "source_ref_id": f"src_{patch_id}",
            "source_registry_id": "rich_leaf_source_gap_candidates",
            "source_dataset_id": source_lane,
            "source_version": "v_demo",
            "extractor_version": "local_test",
            "source_lane": source_lane,
            "path": path,
            "record_id": f"record_{patch_id}",
            "span": span,
            "span_hash": span_hash or source_span_hash(span),
            "matched_terms": matched_terms,
            "retrieval_score": 3.5,
            "provenance": provenance or {},
        },
        "review_packet": {"snippet": span[:120], "question_source_only_not_support": True},
    }


def _patch_batch() -> dict:
    return {
        "schema": "luban_rich_leaf_candidate_patch_batch.v1",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "patches_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "candidate_patches": [
            _patch(
                patch_id="good",
                name_path="建筑设计程序与要求 > 建筑设计程序",
                span="建筑设计程序一般包括方案设计、初步设计、施工图设计等阶段。",
                matched_terms=["建筑设计程序", "初步设计", "施工图设计"],
            ),
            _patch(
                patch_id="hash_bad",
                name_path="建筑设计程序与要求 > 建筑设计程序",
                span="建筑设计程序一般包括方案设计、初步设计、施工图设计等阶段。",
                span_hash="bad-hash",
                matched_terms=["建筑设计程序"],
            ),
            _patch(
                patch_id="option_polluted",
                name_path="建筑设计程序与要求 > 建筑设计程序",
                span="地下连续墙施工特点包括墙体刚度大、抗渗性能好、两墙合一。",
                matched_terms=["A.", "B.", "C.", "D."],
                source_lane="lecture",
                missing_lane="lecture",
                path="讲义/地下连续墙.md",
            ),
            _patch(
                patch_id="weak_overlap",
                name_path="工程预付款与起扣点",
                span="合同价款支付包括预付款、进度款和结算款。",
                matched_terms=["预付款"],
            ),
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_patch_evidence_audit_classifies_machine_pass_reject_and_review() -> None:
    from scripts.run_luban_rich_leaf_patch_evidence_audit import build_patch_evidence_audit

    report = build_patch_evidence_audit(patch_batch=_patch_batch())

    assert report["schema"] == "luban_rich_leaf_patch_evidence_audit.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "audit_apply_allowed": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {
        "audited_patch_count": 4,
        "machine_precheck_pass_count": 1,
        "machine_reject_count": 2,
        "needs_semantic_review_count": 1,
    }
    assert all(value in (False, 0) for value in report["safety"].values())

    by_id = {row["patch_id"]: row for row in report["patch_audits"]}
    assert by_id["good"]["audit_decision"] == "machine_precheck_pass"
    assert by_id["good"]["apply_allowed"] is False
    assert by_id["good"]["runtime_install_allowed"] is False
    assert by_id["hash_bad"]["audit_decision"] == "machine_reject"
    assert "span_hash_mismatch" in by_id["hash_bad"]["reason_codes"]
    assert by_id["option_polluted"]["audit_decision"] == "machine_reject"
    assert "option_marker_only_match" in by_id["option_polluted"]["reason_codes"]
    assert "no_name_path_specific_term_in_span" in by_id["option_polluted"]["reason_codes"]
    assert by_id["weak_overlap"]["audit_decision"] == "needs_semantic_review"
    assert "low_name_path_term_overlap" in by_id["weak_overlap"]["reason_codes"]


def test_cli_writes_patch_evidence_audit(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_patch_evidence_audit import main

    patches_path = tmp_path / "candidate_patches.json"
    output = tmp_path / "audit.json"
    _write_json(patches_path, _patch_batch())

    exit_code = main(["--patches", str(patches_path), "--output", str(output)])

    assert exit_code == 0
    report = json.loads(output.read_text("utf-8"))
    assert report["summary"]["audited_patch_count"] == 4
    assert report["patch_audits"][0]["review_status"] == "machine_precheck_only"
