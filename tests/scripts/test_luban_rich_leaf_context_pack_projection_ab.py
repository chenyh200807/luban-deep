from __future__ import annotations

import copy
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


def _candidate_artifact_batch() -> dict:
    span = "建筑设计一般可分为四个阶段。"
    artifact = {
        "artifact_id": "A1",
        "leaf_id": "L1",
        "bundle_version": "v_test",
        "candidate_status": "reviewed_candidate",
        "source_refs": [_source_ref("src_textbook", "textbook", span)],
        "definitions": [],
        "rules": [
            {
                "field_id": "rule_1",
                "claim_status": "candidate_only",
                "candidate_only": True,
                "review_only": True,
                "source_ref_ids": ["src_textbook"],
                "statement": span,
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
    }
    return {
        "schema": "luban_rich_leaf_artifact_candidate_batch.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "rich_leaf_artifact_candidate_batch": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "artifact_candidate_count": 1,
            "validation_failure_count": 0,
            "field_family_counts": {"rules": 1},
        },
        "rich_leaf_artifact_candidates": [artifact],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _promotion_review_payload() -> dict:
    artifact = copy.deepcopy(_candidate_artifact_batch()["rich_leaf_artifact_candidates"][0])
    artifact["rules"][0]["claim_status"] = "source_backed"
    artifact["rules"][0]["candidate_only"] = False
    return {
        "schema": "luban_rich_leaf_field_promotion_review.v1",
        "input_schema": "luban_rich_leaf_artifact_candidate_batch.v1",
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
            "input_artifact_candidate_count": 1,
            "promoted_artifact_candidate_count": 1,
            "promotion_decision_count": 1,
            "source_backed_field_count": 1,
            "assessment_evidence_field_count": 0,
            "still_candidate_only_field_count": 0,
            "validation_failure_count": 0,
        },
        "promoted_rich_leaf_artifact_candidates": [artifact],
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


def test_projection_ab_shows_promoted_context_gain_without_quality_claim() -> None:
    from scripts.run_luban_rich_leaf_context_pack_projection_ab import run_context_pack_projection_ab

    report = run_context_pack_projection_ab(
        artifact_candidates=_candidate_artifact_batch(),
        field_promotion_review=_promotion_review_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_context_pack_projection_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["quality_claim_allowed"] is False
    assert "live_runtime_accuracy" in report["not_exercised"]
    rows = {row["task"]: row for row in report["effect_table"]}
    assert rows["rag_answer"]["control_field_count"] == 0
    assert rows["rag_answer"]["treatment_field_count"] == 1
    assert rows["rag_answer"]["field_count_delta"] == 1
    assert rows["rag_answer"]["knowledge_task_question_lane_leak"] is False


def test_projection_ab_fails_when_treatment_leaks_question_lane_into_knowledge_task() -> None:
    from scripts.run_luban_rich_leaf_context_pack_projection_ab import run_context_pack_projection_ab

    promotion = _promotion_review_payload()
    artifact = promotion["promoted_rich_leaf_artifact_candidates"][0]
    artifact["source_refs"].append(_source_ref("src_question", "question", "某真题考查建筑设计程序。"))
    artifact["definitions"].append(
        {
            "field_id": "bad_definition",
            "claim_status": "source_backed",
            "candidate_only": False,
            "review_only": True,
            "source_ref_ids": ["src_question"],
            "definition": "真题不应作为知识定义。",
        }
    )

    report = run_context_pack_projection_ab(
        artifact_candidates=_candidate_artifact_batch(),
        field_promotion_review=promotion,
    )

    assert report["verdict"] == "FAIL"
    assert any("treatment_question_lane_source_ref_in_knowledge_task" in blocker for blocker in report["blockers"])


def test_projection_ab_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_context_pack_projection_ab import main

    artifact_candidates = tmp_path / "rich_leaf_artifact_candidates.json"
    promotion_review = tmp_path / "field_promotion_review.json"
    output = tmp_path / "context_pack_projection_ab.json"
    artifact_candidates.write_text(json.dumps(_candidate_artifact_batch(), ensure_ascii=False), encoding="utf-8")
    promotion_review.write_text(json.dumps(_promotion_review_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--artifact-candidates",
            str(artifact_candidates),
            "--field-promotion-review",
            str(promotion_review),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_context_pack_projection_ab.v1"
    assert payload["classification"]["runtime_install_allowed"] is False
