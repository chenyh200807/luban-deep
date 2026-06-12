from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash


def _source_ref(ref_id: str, lane: str, span: str) -> dict:
    return {
        "source_ref_id": ref_id,
        "source_registry_id": "rich_leaf_reviewed_source_refs",
        "source_dataset_id": f"docs2026_{lane}",
        "source_version": "2026.0",
        "extractor_version": "rich_leaf_field_candidate_compiler.v1",
        "source_lane": lane,
        "path": f"{lane}/source.json",
        "record_id": f"{lane.upper()}-1",
        "span": span,
        "span_hash": source_span_hash(span),
    }


def _promotion_review_payload() -> dict:
    textbook_span = "建筑设计一般可分为四个阶段。"
    question_span = "某真题考查建筑设计程序。"
    return {
        "schema": "luban_rich_leaf_field_promotion_review.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "field_promotion_review": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_artifact_candidate_count": 2,
            "promoted_artifact_candidate_count": 2,
            "promotion_decision_count": 2,
            "source_backed_field_count": 1,
            "assessment_evidence_field_count": 1,
            "still_candidate_only_field_count": 0,
            "validation_failure_count": 0,
        },
        "promoted_rich_leaf_artifact_candidates": [
            {
                "artifact_id": "A-textbook",
                "leaf_id": "L1",
                "bundle_version": "v_test",
                "candidate_status": "reviewed_candidate",
                "source_refs": [_source_ref("src_textbook", "textbook", textbook_span)],
                "definitions": [],
                "rules": [
                    {
                        "field_id": "rule_1",
                        "claim_status": "source_backed",
                        "candidate_only": False,
                        "review_only": True,
                        "source_ref_ids": ["src_textbook"],
                        "statement": textbook_span,
                    }
                ],
                "procedures": [],
                "numeric_constraints": [],
                "negative_evidence": [],
                "teaching_cards": [],
                "rubric_link_index": [],
                "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
                "exam_patterns": [],
                "learner_memory_event_templates": [],
            },
            {
                "artifact_id": "A-question",
                "leaf_id": "L2",
                "bundle_version": "v_test",
                "candidate_status": "reviewed_candidate",
                "source_refs": [_source_ref("src_question", "question", question_span)],
                "definitions": [],
                "rules": [],
                "procedures": [],
                "numeric_constraints": [],
                "negative_evidence": [],
                "teaching_cards": [],
                "rubric_link_index": [],
                "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
                "exam_patterns": [
                    {
                        "field_id": "exam_pattern_1",
                        "claim_status": "assessment_evidence",
                        "candidate_only": False,
                        "review_only": True,
                        "source_ref_ids": ["src_question"],
                        "pattern_type": "question_lane_evidence",
                        "knowledge_source_allowed": False,
                    }
                ],
                "learner_memory_event_templates": [],
            },
            {
                "artifact_id": "A-negative",
                "leaf_id": "L3",
                "bundle_version": "v_test",
                "candidate_status": "reviewed_candidate",
                "source_refs": [_source_ref("src_negative", "textbook", "该段只说明父级路径，不说明当前 leaf 的具体术语。")],
                "definitions": [],
                "rules": [],
                "procedures": [],
                "numeric_constraints": [],
                "negative_evidence": [
                    {
                        "field_id": "neg_1",
                        "claim_status": "candidate_only",
                        "candidate_only": True,
                        "review_only": True,
                        "source_ref_ids": ["src_negative"],
                        "negative_evidence_type": "wrong_leaf_source",
                        "positive_context_allowed": False,
                    }
                ],
                "teaching_cards": [],
                "rubric_link_index": [],
                "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
                "exam_patterns": [],
                "learner_memory_event_templates": [],
            },
        ],
        "promotion_decisions": [],
        "validation_reports": [],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_context_pack_smoke_blocks_question_lane_from_rag_and_tutoring() -> None:
    from scripts.run_luban_rich_leaf_context_pack_smoke import run_context_pack_smoke

    report = run_context_pack_smoke(field_promotion_review=_promotion_review_payload())

    assert report["schema"] == "luban_rich_leaf_context_pack_smoke.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    by_task = {pack["task"]: pack for pack in report["compiled_context_packs"]}
    assert by_task["rag_answer"]["source_ref_lanes"] == ["textbook"]
    assert by_task["tutoring"]["source_ref_lanes"] == ["textbook"]
    assert by_task["grading"]["source_ref_lanes"] == ["textbook"]
    assert by_task["next_action"]["source_ref_lanes"] == ["question"]
    assert by_task["review"]["review_candidate_field_count"] == 1
    assert by_task["review"]["review_candidate_field_ids"] == ["neg_1"]
    assert by_task["review"]["source_ref_lanes"] == ["textbook"]
    assert report["summary"]["review_candidate_field_count"] == 1


def test_context_pack_smoke_reports_polluted_rag_source_ref() -> None:
    from scripts.run_luban_rich_leaf_context_pack_smoke import run_context_pack_smoke

    payload = _promotion_review_payload()
    payload["promoted_rich_leaf_artifact_candidates"][1]["definitions"].append(
        {
            "field_id": "bad_definition",
            "claim_status": "source_backed",
            "candidate_only": False,
            "review_only": True,
            "source_ref_ids": ["src_question"],
            "definition": "真题不能作为知识定义。",
        }
    )

    report = run_context_pack_smoke(field_promotion_review=payload)

    assert report["verdict"] == "FAIL"
    assert any("question_lane_source_ref_in_knowledge_task" in blocker for blocker in report["blockers"])


def test_context_pack_smoke_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_context_pack_smoke import main

    promotion_review = tmp_path / "field_promotion_review.json"
    output = tmp_path / "context_pack_smoke.json"
    promotion_review.write_text(json.dumps(_promotion_review_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--field-promotion-review", str(promotion_review), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_context_pack_smoke.v1"
    assert payload["summary"]["task_pack_count"] == 5
