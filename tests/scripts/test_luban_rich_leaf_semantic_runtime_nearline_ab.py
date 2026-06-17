from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash


def _source_ref(ref_id: str, span: str, lane: str = "textbook") -> dict:
    return {
        "source_ref_id": ref_id,
        "source_registry_id": "rich_leaf_reviewed_source_refs",
        "source_dataset_id": f"docs2026_{lane}",
        "source_version": "2026.0",
        "extractor_version": "rich_leaf_field_candidate_compiler.v1",
        "source_lane": lane,
        "path": f"{lane}/source.json",
        "record_id": f"{lane.upper()}-{ref_id}",
        "span": span,
        "span_hash": source_span_hash(span),
    }


def _promotion_review_payload() -> dict:
    target_span = "建筑设计一般可分为四个阶段：方案设计、初步设计、技术设计和施工图设计。"
    distractor_span = "施工现场临时用电应符合安全管理要求。"
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
        "promoted_rich_leaf_artifact_candidates": [
            {
                "artifact_id": "A1",
                "leaf_id": "L1",
                "bundle_version": "v_test",
                "candidate_status": "reviewed_candidate",
                "source_refs": [_source_ref("src_target", target_span), _source_ref("src_noise", distractor_span)],
                "definitions": [],
                "rules": [
                    {
                        "field_id": "rule_1",
                        "claim_status": "source_backed",
                        "candidate_only": False,
                        "review_only": True,
                        "source_ref_ids": ["src_target"],
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


def test_nearline_ab_compares_current_rag_projection_and_promoted_context() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_nearline_ab import run_semantic_runtime_nearline_ab

    report = run_semantic_runtime_nearline_ab(field_promotion_review=_promotion_review_payload(), top_k=2)

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_nearline_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["verdict_ceiling"] == "NEARLINE_RETRIEVAL_PROJECTION"
    assert report["quality_claim_allowed"] is False
    assert "production_rag_retrieval" in report["not_exercised"]
    by_arm = {arm["arm"]: arm for arm in report["effect_table"]}
    assert by_arm["baseline_empty_context"]["abstention_rate"] == 1.0
    assert by_arm["current_rag_lexical_retrieval"]["answerable_rate"] == 1.0
    assert by_arm["rich_leaf_promoted_context"]["answerable_rate"] == 1.0
    assert by_arm["rich_leaf_promoted_context"]["mean_token_proxy"] < by_arm["current_rag_lexical_retrieval"]["mean_token_proxy"]
    assert by_arm["rich_leaf_promoted_context"]["fail_open_rate"] == 0.0


def test_nearline_ab_blocks_promoted_context_question_lane_leak() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_nearline_ab import run_semantic_runtime_nearline_ab

    payload = _promotion_review_payload()
    source_ref = payload["promoted_rich_leaf_artifact_candidates"][0]["source_refs"][0]
    source_ref["source_lane"] = "question"
    source_ref["source_dataset_id"] = "docs2026_question"

    report = run_semantic_runtime_nearline_ab(field_promotion_review=payload)

    assert report["verdict"] == "FAIL"
    assert any("question_lane_source_backed_knowledge_field" in blocker for blocker in report["blockers"])


def test_nearline_ab_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_nearline_ab import main

    promotion_review = tmp_path / "field_promotion_review.json"
    output = tmp_path / "semantic_runtime_nearline_ab.json"
    promotion_review.write_text(json.dumps(_promotion_review_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--field-promotion-review", str(promotion_review), "--output", str(output), "--top-k", "2"])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_nearline_ab.v1"
    assert payload["classification"]["runtime_install_allowed"] is False
