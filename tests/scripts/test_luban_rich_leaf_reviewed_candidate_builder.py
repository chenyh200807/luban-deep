from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _audit_record(decision: str | None = None) -> dict:
    review_status = "recorded" if decision else "not_exercised"
    return {
        "schema": "luban_rich_leaf_semantic_evidence_audit_record.v1",
        "classification": {
            "review_only": True,
            "semantic_verdict_recorded": bool(decision),
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "semantic_evidence_audit_records": [
            {
                "audit_item_id": "audit_queue:patch:P1",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "textbook",
                "review_decision_status": review_status,
                "decision": decision,
                "reviewer_role": "evidence_auditor" if decision else None,
                "reviewer_id": "ai_shadow" if decision else None,
                "rationale": "Source span supports the exact leaf." if decision else None,
                "confidence": "medium" if decision else None,
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "教材/book.json",
                    "record_id": "TB1",
                    "span": "初步设计文件包括工程概算书。",
                    "span_hash": "hash1",
                    "matched_terms": ["初步设计", "工程概算书"],
                    "support_candidate": True,
                },
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
                "official_score_allowed": False,
            }
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_reviewed_candidate_builder_outputs_zero_without_accepted_decisions() -> None:
    from scripts.run_luban_rich_leaf_reviewed_candidate_builder import build_reviewed_candidate_report

    report = build_reviewed_candidate_report(audit_record=_audit_record())

    assert report["schema"] == "luban_rich_leaf_reviewed_candidate_batch.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }
    assert report["summary"] == {
        "audit_record_count": 1,
        "accepted_source_ref_count": 0,
        "reviewed_candidate_count": 0,
        "not_accepted_count": 1,
    }
    assert report["reviewed_candidates"] == []
    assert all(value in (False, 0) for value in report["safety"].values())


def test_reviewed_candidate_builder_creates_reviewed_source_ref_candidate_from_accept_decision() -> None:
    from scripts.run_luban_rich_leaf_reviewed_candidate_builder import build_reviewed_candidate_report

    report = build_reviewed_candidate_report(audit_record=_audit_record("accept_source_ref_candidate"))

    assert report["summary"]["accepted_source_ref_count"] == 1
    assert report["summary"]["reviewed_candidate_count"] == 1
    candidate = report["reviewed_candidates"][0]
    assert candidate["candidate_status"] == "reviewed_candidate"
    assert candidate["leaf_id"] == "L1"
    assert candidate["field_patch"]["field"] == "source_refs"
    assert candidate["field_patch"]["operation"] == "add_source_ref"
    assert candidate["field_patch"]["source_ref"]["record_id"] == "TB1"
    assert candidate["review_authority"]["decision"] == "accept_source_ref_candidate"
    assert candidate["runtime_install_allowed"] is False
    assert candidate["release_truth_claimed"] is False


def test_reviewed_candidate_builder_cli_writes_zero_candidate_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_reviewed_candidate_builder import main

    audit_record_path = tmp_path / "semantic_evidence_audit_record.json"
    output_dir = tmp_path / "out"
    _write_json(audit_record_path, _audit_record())

    exit_code = main(["--audit-record", str(audit_record_path), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "reviewed_rich_leaf_candidates.json").read_text("utf-8"))
    assert report["summary"]["reviewed_candidate_count"] == 0
    assert report["classification"]["runtime_install_allowed"] is False
