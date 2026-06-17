from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash


def _source_ref(ref_id: str = "src_textbook", lane: str = "textbook") -> dict:
    span = "建筑设计一般可分为四个阶段：方案设计、初步设计、技术设计和施工图设计。"
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


def _promotion_review_payload(*, lane: str = "textbook") -> dict:
    source_ref = _source_ref(lane=lane)
    artifact = {
        "artifact_id": "A1",
        "leaf_id": "L1",
        "bundle_version": "v_test",
        "candidate_status": "reviewed_candidate",
        "source_refs": [source_ref],
        "definitions": [],
        "rules": [
            {
                "field_id": "rule_1",
                "claim_status": "source_backed",
                "candidate_only": False,
                "review_only": True,
                "source_ref_ids": [source_ref["source_ref_id"]],
                "statement": "建筑设计一般可分为四个阶段",
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


def test_semantic_runtime_offline_ab_treatment_uses_evidence_without_quality_claim() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_offline_ab import run_semantic_runtime_offline_ab

    report = run_semantic_runtime_offline_ab(field_promotion_review=_promotion_review_payload())

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_offline_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["verdict_ceiling"] == "OFFLINE_ADAPTER_ONLY"
    assert report["quality_claim_allowed"] is False
    assert "live_llm_semantic_judgment" in report["not_exercised"]
    by_arm = {arm["arm"]: arm for arm in report["effect_table"]}
    assert by_arm["baseline_empty_context"]["abstention_rate"] == 1.0
    assert by_arm["baseline_empty_context"]["fail_open_rate"] == 0.0
    assert by_arm["rich_leaf_promoted_context"]["evidence_citation_rate"] == 1.0
    assert by_arm["rich_leaf_promoted_context"]["answerable_rate"] == 1.0


def test_semantic_runtime_offline_ab_routes_teaching_cards_to_tutoring_pack() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_offline_ab import run_semantic_runtime_offline_ab

    payload = _promotion_review_payload()
    artifact = payload["promoted_rich_leaf_artifact_candidates"][0]
    artifact["teaching_cards"].append(
        {
            "field_id": "card_1",
            "claim_status": "source_backed",
            "candidate_only": False,
            "review_only": True,
            "source_ref_ids": ["src_textbook"],
            "card": "用四阶段顺序理解建筑设计程序。",
            "source_excerpt": "建筑设计一般可分为四个阶段：方案设计、初步设计、技术设计和施工图设计。",
            "not_for_official_scoring": True,
        }
    )

    report = run_semantic_runtime_offline_ab(field_promotion_review=payload)

    assert report["verdict"] == "PASS"
    assert report["summary"]["eval_case_count"] == 2
    by_arm = {arm["arm"]: arm for arm in report["effect_table"]}
    assert by_arm["rich_leaf_promoted_context"]["answerable_rate"] == 1.0
    treatment_rows = [row for row in report["sample_rows"] if row["arm"] == "rich_leaf_promoted_context"]
    assert {row["task"] for row in treatment_rows} == {"rag_answer", "tutoring"}


def test_semantic_runtime_offline_ab_blocks_question_lane_knowledge_context() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_offline_ab import run_semantic_runtime_offline_ab

    payload = _promotion_review_payload(lane="question")

    report = run_semantic_runtime_offline_ab(field_promotion_review=payload)

    assert report["verdict"] == "FAIL"
    assert any("question_lane_source_backed_knowledge_field" in blocker for blocker in report["blockers"])


def test_semantic_runtime_offline_ab_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_offline_ab import main

    promotion_review = tmp_path / "field_promotion_review.json"
    output = tmp_path / "semantic_runtime_offline_ab.json"
    promotion_review.write_text(json.dumps(_promotion_review_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--field-promotion-review", str(promotion_review), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_offline_ab.v1"
    assert payload["classification"]["runtime_install_allowed"] is False
