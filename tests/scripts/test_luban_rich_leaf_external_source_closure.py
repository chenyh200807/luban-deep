from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _semantic_record() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_evidence_audit_record.v1",
        "classification": {
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "semantic_evidence_audit_records": [
            {
                "audit_item_id": "item-1",
                "leaf_id": "leaf-001",
                "artifact_id": "artifact-001",
                "field": "rules",
                "lane": "textbook",
                "decision": "needs_external_source",
                "decision_status": "recorded",
                "terms": ["工程预付款", "起扣点"],
                "review_note": "No local textbook/standard support found yet.",
            },
            {
                "audit_item_id": "item-2",
                "leaf_id": "leaf-002",
                "artifact_id": "artifact-002",
                "field": "definitions",
                "lane": "textbook",
                "decision": "accept_source_ref_candidate",
                "decision_status": "recorded",
                "terms": ["流水施工"],
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


def test_external_source_closure_searches_only_needs_external_source_and_remains_review_only(
    tmp_path: Path,
) -> None:
    from scripts.run_luban_rich_leaf_external_source_closure import build_external_source_closure_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "2026教材" / "费用控制" / "book.json",
        [{"record_id": "TB-1", "text": "工程预付款的起扣点应按合同约定和主要材料占比计算。"}],
    )
    _write_json(
        docs_root / "题库" / "case.json",
        [{"record_id": "Q-1", "question": "工程预付款起扣点如何计算？", "answer": "按主要材料占比。"}],
    )

    report = build_external_source_closure_report(
        semantic_record=_semantic_record(),
        docs_root=docs_root,
        top_k=3,
    )

    assert report["schema"] == "luban_rich_leaf_external_source_closure.v1"
    assert report["input_schemas"] == {
        "semantic_evidence_audit_record": "luban_rich_leaf_semantic_evidence_audit_record.v1"
    }
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "external_source_closure": True,
        "source_truth_claimed": False,
        "runtime_install_allowed": False,
        "production_default": False,
        "release_truth_claimed": False,
        "quality_claim_allowed": False,
    }
    assert all(value in (False, 0) for value in report["safety"].values())
    assert report["summary"]["needs_external_source_count"] == 1
    assert report["summary"]["closure_candidate_count"] == 1
    assert report["summary"]["question_context_candidate_count"] == 0
    assert report["summary"]["source_truth_write_count"] == 0

    closure = report["external_source_closures"][0]
    assert closure["audit_item_id"] == "item-1"
    assert closure["status"] == "candidate_sources_found"
    assert closure["candidate_sources"][0]["source_lane"] == "textbook"
    assert closure["candidate_sources"][0]["support_candidate"] is True
    assert closure["candidate_sources"][0]["install_allowed"] is False
    assert closure["question_context_candidates"] == []


def test_external_source_closure_keeps_question_matches_as_context_only(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_external_source_closure import build_external_source_closure_report

    docs_root = tmp_path / "docs2026"
    _write_json(
        docs_root / "题库" / "case.json",
        [
            {
                "content_type": "exercise",
                "record_id": "Q-1",
                "text": "工程预付款起扣点如何计算？按主要材料占比。",
            }
        ],
    )

    report = build_external_source_closure_report(
        semantic_record=_semantic_record(),
        docs_root=docs_root,
        top_k=3,
    )

    closure = report["external_source_closures"][0]
    assert closure["status"] == "external_source_required"
    assert closure["candidate_sources"] == []
    assert closure["question_context_candidates"][0]["source_lane"] == "question"
    assert closure["question_context_candidates"][0]["support_candidate"] is False
    assert report["summary"]["closure_candidate_count"] == 0
    assert report["summary"]["external_source_required_count"] == 1


def test_external_source_closure_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_external_source_closure import main

    docs_root = tmp_path / "docs2026"
    _write_json(docs_root / "标准文件" / "std.json", [{"record_id": "STD-1", "text": "工程预付款起扣点可依据合同约定。"}])
    semantic_record_path = tmp_path / "semantic_evidence_audit_record.json"
    output_dir = tmp_path / "out"
    _write_json(semantic_record_path, _semantic_record())

    exit_code = main(
        [
            "--semantic-record",
            str(semantic_record_path),
            "--docs-root",
            str(docs_root),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "external_source_closure.json").read_text("utf-8"))
    assert report["verdict"] == "PASS"
    assert report["summary"]["needs_external_source_count"] == 1
