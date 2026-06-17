from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _semantic_queue() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_audit_queue.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "semantic_audit_queue": [
            {
                "audit_item_id": "audit_queue:patch:P1",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "textbook",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "教材/book.json",
                    "record_id": "TB1",
                    "span": "初步设计文件包括工程概算书。",
                    "span_hash": "hash1",
                    "support_candidate": True,
                },
                "question_context_candidates": [],
                "review_status": "semantic_review_pending",
                "semantic_verdict_recorded": False,
                "candidate_only": True,
                "review_only": True,
                "apply_allowed": False,
                "runtime_install_allowed": False,
            },
            {
                "audit_item_id": "audit_queue:unresolved:A2:standard",
                "audit_source_type": "source_evidence_unresolved",
                "leaf_id": "L2",
                "artifact_id": "A2",
                "missing_lane": "standard",
                "source_candidate": None,
                "question_context_candidates": [
                    {
                        "source_lane": "question",
                        "record_id": "Q2",
                        "span": "某案例题考查工程进度款支付。",
                        "span_hash": "hash2",
                        "support_candidate": False,
                    }
                ],
                "review_status": "semantic_review_pending",
                "semantic_verdict_recorded": False,
                "candidate_only": True,
                "review_only": True,
                "apply_allowed": False,
                "runtime_install_allowed": False,
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


def _decisions() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_audit_decisions.v1",
        "decisions": [
            {
                "audit_item_id": "audit_queue:patch:P1",
                "decision": "accept_source_ref_candidate",
                "reviewer_role": "evidence_auditor",
                "reviewer_id": "ai_review_shadow",
                "rationale": "The span explicitly supports the leaf-level source reference.",
                "confidence": "medium",
            }
        ],
    }


def test_semantic_evidence_audit_record_marks_all_items_not_exercised_without_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_evidence_audit_record import build_semantic_evidence_audit_record_report

    report = build_semantic_evidence_audit_record_report(semantic_queue=_semantic_queue(), decisions=None)

    assert report["schema"] == "luban_rich_leaf_semantic_evidence_audit_record.v1"
    assert report["classification"] == {
        "review_only": True,
        "semantic_verdict_recorded": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }
    assert report["summary"] == {
        "audit_item_count": 2,
        "decision_record_count": 0,
        "not_exercised_count": 2,
        "invalid_decision_count": 0,
    }
    assert all(record["review_decision_status"] == "not_exercised" for record in report["semantic_evidence_audit_records"])
    assert all(record["runtime_install_allowed"] is False for record in report["semantic_evidence_audit_records"])
    assert all(value in (False, 0) for value in report["safety"].values())


def test_semantic_evidence_audit_record_records_valid_decisions_without_runtime_authority() -> None:
    from scripts.run_luban_rich_leaf_semantic_evidence_audit_record import build_semantic_evidence_audit_record_report

    report = build_semantic_evidence_audit_record_report(semantic_queue=_semantic_queue(), decisions=_decisions())

    assert report["classification"]["semantic_verdict_recorded"] is True
    assert report["summary"] == {
        "audit_item_count": 2,
        "decision_record_count": 1,
        "not_exercised_count": 1,
        "invalid_decision_count": 0,
    }
    decided = report["semantic_evidence_audit_records"][0]
    assert decided["review_decision_status"] == "recorded"
    assert decided["decision"] == "accept_source_ref_candidate"
    assert decided["reviewer_role"] == "evidence_auditor"
    assert decided["runtime_install_allowed"] is False
    assert decided["release_truth_claimed"] is False


def test_semantic_evidence_audit_record_cli_writes_not_exercised_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_evidence_audit_record import main

    queue_path = tmp_path / "semantic_audit_queue.json"
    output_dir = tmp_path / "out"
    _write_json(queue_path, _semantic_queue())

    exit_code = main(["--semantic-queue", str(queue_path), "--output-dir", str(output_dir), "--no-decisions"])

    assert exit_code == 0
    report = json.loads((output_dir / "semantic_evidence_audit_record.json").read_text("utf-8"))
    assert report["summary"]["not_exercised_count"] == 2
    assert report["classification"]["semantic_verdict_recorded"] is False


def test_semantic_evidence_audit_record_cli_uses_default_merged_decisions(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.run_luban_rich_leaf_semantic_evidence_audit_record as module

    queue_path = tmp_path / "semantic_audit_queue.json"
    decisions_path = tmp_path / "merged_semantic_audit_decisions.json"
    output_dir = tmp_path / "out"
    _write_json(queue_path, _semantic_queue())
    _write_json(decisions_path, _decisions())
    monkeypatch.setattr(module, "DEFAULT_DECISIONS", decisions_path)

    exit_code = module.main(["--semantic-queue", str(queue_path), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "semantic_evidence_audit_record.json").read_text("utf-8"))
    assert report["summary"]["decision_record_count"] == 1
    assert report["summary"]["not_exercised_count"] == 1
