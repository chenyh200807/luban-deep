from __future__ import annotations

import json
from pathlib import Path


def _reviewed_candidate(lane: str, span: str) -> dict:
    return {
        "candidate_id": f"RC-{lane}",
        "candidate_status": "reviewed_candidate",
        "leaf_id": f"L-{lane}",
        "artifact_id": f"A-{lane}",
        "missing_lane": lane,
        "audit_item_id": f"audit:{lane}",
        "field_patch": {
            "field": "source_refs",
            "operation": "add_source_ref",
            "source_ref": {
                "source_lane": lane,
                "source_path": f"{lane}/source.json",
                "record_id": f"{lane.upper()}-1",
                "span": span,
                "span_hash": f"hash-{lane}",
                "matched_terms": ["混凝土", "施工"],
                "support_candidate": True,
            },
        },
        "review_authority": {
            "review_decision_status": "recorded",
            "decision": "accept_source_ref_candidate",
            "reviewer_role": "semantic_evidence_reviewer",
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def _reviewed_batch(*candidates: dict) -> dict:
    return {
        "schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_record_count": len(candidates),
            "accepted_source_ref_count": len(candidates),
            "reviewed_candidate_count": len(candidates),
            "not_accepted_count": 0,
        },
        "reviewed_candidates": list(candidates),
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _semantic_record(decision: str = "reject_wrong_leaf_source", lane: str = "textbook") -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_evidence_audit_record.v1",
        "summary": {
            "audit_item_count": 1,
            "decision_record_count": 1,
            "invalid_decision_count": 0,
            "not_exercised_count": 0,
        },
        "semantic_evidence_audit_records": [
            {
                "artifact_id": f"A-reject-{lane}",
                "audit_item_id": f"audit:reject:{lane}",
                "audit_source_type": "patch_semantic_packet",
                "candidate_only": True,
                "decision": decision,
                "leaf_id": f"L-reject-{lane}",
                "missing_lane": lane,
                "official_score_allowed": False,
                "rationale": "候选来源只命中父级路径，不支撑当前 leaf 的具体术语。",
                "release_truth_claimed": False,
                "review_decision_status": "recorded",
                "review_only": True,
                "reviewer_role": "semantic_evidence_reviewer",
                "runtime_install_allowed": False,
                "source_candidate": {
                    "candidate_only": True,
                    "install_allowed": False,
                    "matched_terms": ["父级路径", "具体术语"],
                    "record_id": f"{lane.upper()}-REJECT-1",
                    "runtime_install_allowed": False,
                    "source_lane": lane,
                    "source_path": f"{lane}/reject_source.json",
                    "span": "该段只说明父级路径，不说明当前 leaf 的具体术语。",
                    "span_hash": f"hash-reject-{lane}",
                    "support_candidate": True,
                },
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


def test_field_candidate_compiler_extracts_source_backed_candidates_from_non_question_span() -> None:
    from scripts.run_luban_rich_leaf_field_candidate_compiler import compile_field_candidates

    span = "根据基础深度宜分段分层（300～500mm）连续浇筑混凝土，一般不留施工缝。每段间浇筑长度控制在 2～3m。"
    report = compile_field_candidates(reviewed_candidates=_reviewed_batch(_reviewed_candidate("textbook", span)))

    assert report["schema"] == "luban_rich_leaf_field_candidate_batch.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    families = {candidate["family"] for candidate in report["field_candidates"]}
    assert {
        "concepts",
        "rules",
        "procedures",
        "numeric_constraints",
        "teaching_cards",
        "common_mistakes",
        "learner_memory_event_templates",
    } <= families
    assert "exam_patterns" not in families
    concept = [candidate for candidate in report["field_candidates"] if candidate["family"] == "concepts"][0]
    assert concept["concept_name"] == "混凝土"
    assert concept["aliases"] == ["施工"]
    numeric = [candidate for candidate in report["field_candidates"] if candidate["family"] == "numeric_constraints"]
    assert numeric
    assert any("300～500mm" in item["value"] for item in numeric[0]["items"])
    template = [
        candidate for candidate in report["field_candidates"] if candidate["family"] == "learner_memory_event_templates"
    ][0]
    assert template["event_type"] == "case_grading_completed"
    assert template["template_status"] == "candidate_only_not_writeable"
    assert template["canonical_write_allowed"] is False
    mistake = [candidate for candidate in report["field_candidates"] if candidate["family"] == "common_mistakes"][0]
    assert mistake["mistake_group"] == "hypothesized_mistakes"
    assert mistake["observed_from"] == "synthetic_candidate"
    assert mistake["claim_status"] == "candidate_only"
    assert mistake["learner_evidence_allowed"] is False
    assert mistake["mistake_type"] == "missing_or_confused_key_term"
    assert report["summary"]["source_backed_knowledge_candidate_count"] == 5
    assert all(candidate["claim_status"] == "candidate_only" for candidate in report["field_candidates"])
    assert all(candidate["source_ref_trace"]["source_lane"] == "textbook" for candidate in report["field_candidates"])


def test_field_candidate_compiler_keeps_question_lane_out_of_source_backed_fields() -> None:
    from scripts.run_luban_rich_leaf_field_candidate_compiler import compile_field_candidates

    span = "第1题 下列施工工序中,属于钢筋加工工作内容的有( )。答案 BDE。"
    report = compile_field_candidates(reviewed_candidates=_reviewed_batch(_reviewed_candidate("question", span)))

    families = [candidate["family"] for candidate in report["field_candidates"]]
    assert families == ["exam_patterns"]
    assert report["field_candidates"][0]["claim_status"] == "candidate_only"
    assert report["field_candidates"][0]["source_ref_trace"]["source_lane"] == "question"
    assert report["summary"]["source_backed_knowledge_candidate_count"] == 0


def test_field_candidate_compiler_derives_negative_evidence_from_rejected_semantic_records() -> None:
    from scripts.run_luban_rich_leaf_field_candidate_compiler import compile_field_candidates

    report = compile_field_candidates(
        reviewed_candidates=_reviewed_batch(),
        semantic_evidence_audit_record=_semantic_record(),
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["negative_evidence_candidate_count"] == 1
    field = report["field_candidates"][0]
    assert field["family"] == "negative_evidence"
    assert field["claim_status"] == "candidate_only"
    assert field["negative_evidence_type"] == "wrong_leaf_source"
    assert field["source_ref_trace"]["source_lane"] == "textbook"
    assert field["runtime_install_allowed"] is False
    assert field["release_truth_claimed"] is False


def test_field_candidate_compiler_does_not_turn_question_rejects_into_knowledge_negative_evidence() -> None:
    from scripts.run_luban_rich_leaf_field_candidate_compiler import compile_field_candidates

    report = compile_field_candidates(
        reviewed_candidates=_reviewed_batch(),
        semantic_evidence_audit_record=_semantic_record(lane="question"),
    )

    assert report["field_candidates"] == []
    assert report["summary"]["negative_evidence_candidate_count"] == 0


def test_field_candidate_compiler_cli_writes_review_only_artifact(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_field_candidate_compiler import main

    reviewed = tmp_path / "reviewed_rich_leaf_candidates.json"
    out_dir = tmp_path / "out"
    reviewed.write_text(
        json.dumps(_reviewed_batch(_reviewed_candidate("standard", "施工单位应建立安全生产制度。")), ensure_ascii=False),
        encoding="utf-8",
    )
    semantic_record = tmp_path / "semantic_evidence_audit_record.json"
    semantic_record.write_text(json.dumps(_semantic_record(lane="standard"), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--reviewed-candidates",
            str(reviewed),
            "--semantic-record",
            str(semantic_record),
            "--output-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    payload = json.loads((out_dir / "rich_leaf_field_candidates.json").read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_field_candidate_batch.v1"
    assert payload["classification"]["review_only"] is True
    assert payload["summary"]["negative_evidence_candidate_count"] == 1
    assert payload["safety"]["installed_runtime_supply"] is False
