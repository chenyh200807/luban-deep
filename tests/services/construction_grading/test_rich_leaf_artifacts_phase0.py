from __future__ import annotations

import hashlib

from deeptutor.services.construction_grading.rich_leaf_artifacts import (
    COMPILED_CONTEXT_PACK_V0_SCHEMA,
    RICH_LEAF_ARTIFACT_V0_SCHEMA,
    build_compiled_context_pack,
    normalize_source_span,
    source_span_hash,
    validate_rich_leaf_artifact,
)
from deeptutor.services.construction_grading.rich_leaf_workbench_contracts import (
    RICH_LEAF_WORKBENCH_STAGE_CONTRACTS,
    RICH_LEAF_WORKBENCH_STAGE_SCHEMAS,
    get_rich_leaf_workbench_schema,
    ordered_rich_leaf_workbench_stage_names,
)


def _source_ref(ref_id: str = "src_1") -> dict:
    return {
        "source_ref_id": ref_id,
        "source_registry_id": "docs2026_registry",
        "source_dataset_id": "textbook_2026",
        "source_version": "2026.0",
        "extractor_version": "extractor.v1",
        "source_lane": "textbook",
        "path": "docs/2026/textbook.md",
        "record_id": "1A411011:block-1",
        "span": " 建筑物由结构体系、围护体系和设备体系组成。 ",
        "span_hash": source_span_hash("建筑物由结构体系、围护体系和设备体系组成。"),
    }


def _valid_artifact() -> dict:
    return {
        "artifact_id": "leaf_1A411011",
        "leaf_id": "1A411011-01-a",
        "bundle_version": "v_rich_leaf_candidate_20260611",
        "candidate_status": "reviewed_candidate",
        "source_refs": [_source_ref()],
        "rules": [
            {
                "field_id": "rule_1",
                "claim_status": "source_backed",
                "source_ref_ids": ["src_1"],
                "rule_type": "mandatory",
                "statement": "建筑物构成应区分结构、围护、设备体系。",
            }
        ],
        "concepts": [
            {
                "field_id": "concept_1",
                "claim_status": "source_backed",
                "source_ref_ids": ["src_1"],
                "name": "建筑物组成体系",
                "aliases": ["结构体系、围护体系、设备体系"],
            }
        ],
        "numeric_constraints": [],
        "rubric_link_index": [
            {
                "field_id": "rubric_link_1",
                "claim_status": "source_backed",
                "source_ref_ids": ["src_1"],
                "scoring_artifact_id": "case_rubric_v1",
                "rubric_version": "2026.case.v1",
                "scoring_point_ids": ["P1"],
                "link_status": "reviewed_candidate",
            }
        ],
        "common_mistakes": {
            "observed_mistakes": [
                {
                    "field_id": "mistake_1",
                    "claim_status": "learner_evidence",
                    "observed_from": "teacher_final",
                    "evidence_refs": ["grading_event_1"],
                    "mistake_type": "missing_item",
                }
            ],
            "hypothesized_mistakes": [
                {
                    "field_id": "mistake_h1",
                    "claim_status": "candidate_only",
                    "observed_from": "council_shadow",
                    "mistake_type": "near_synonym",
                }
            ],
        },
        "teaching_cards": [
            {
                "field_id": "card_1",
                "claim_status": "candidate_only",
                "source_ref_ids": ["src_1"],
                "card": "结构、围护、设备是建筑物构成的常见三分法。",
            }
        ],
    }


def test_phase0_schema_contract_excludes_controlled_default_from_artifact_status() -> None:
    status_enum = RICH_LEAF_ARTIFACT_V0_SCHEMA["properties"]["candidate_status"]["enum"]
    assert "candidate" in status_enum
    assert "reviewed_candidate" in status_enum
    assert "release_candidate" in status_enum
    assert "controlled_default" not in status_enum
    assert "concepts" in RICH_LEAF_ARTIFACT_V0_SCHEMA["properties"]
    assert "exam_patterns" in RICH_LEAF_ARTIFACT_V0_SCHEMA["properties"]
    assert "grading_relevance" not in RICH_LEAF_ARTIFACT_V0_SCHEMA["properties"]
    assert "rubric_link_index" in RICH_LEAF_ARTIFACT_V0_SCHEMA["properties"]
    assert "source_refs" in RICH_LEAF_ARTIFACT_V0_SCHEMA["required"]
    assert COMPILED_CONTEXT_PACK_V0_SCHEMA["properties"]["canonical_write_allowed"]["const"] is False
    assert COMPILED_CONTEXT_PACK_V0_SCHEMA["properties"]["official_score_allowed"]["const"] is False


def test_workbench_stage_contract_registry_is_single_schema_authority() -> None:
    stage_names = ordered_rich_leaf_workbench_stage_names()
    stage_orders = [contract.order for contract in RICH_LEAF_WORKBENCH_STAGE_CONTRACTS]

    assert len(stage_names) >= 30
    assert len(stage_names) == len(set(stage_names))
    assert stage_orders == sorted(stage_orders)
    assert len(stage_orders) == len(set(stage_orders))
    assert set(stage_names) == set(RICH_LEAF_WORKBENCH_STAGE_SCHEMAS)
    assert get_rich_leaf_workbench_schema("semantic_runtime_live_ab") == "luban_rich_leaf_semantic_runtime_live_ab.v1"
    assert get_rich_leaf_workbench_schema("learning_evidence_candidate_bridge") == (
        "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
    )
    assert "controlled_default" not in RICH_LEAF_WORKBENCH_STAGE_SCHEMAS


def test_source_span_hash_uses_stable_normalization_without_dropping_chinese_punctuation() -> None:
    assert normalize_source_span("Ａ  ＝  1\n\n，。") == "A = 1 ,。"
    digest = source_span_hash("Ａ  ＝  1\n\n，。")
    assert digest == hashlib.sha256("A = 1 ,。".encode("utf-8")).hexdigest()


def test_validator_rejects_artifact_self_promotion_and_rubric_policy_copy() -> None:
    artifact = _valid_artifact()
    artifact["candidate_status"] = "controlled_default"
    artifact["rubric_link_index"][0]["policy_type"] = "exact_required"
    artifact["rubric_link_index"][0]["required_terms"] = ["结构体系"]

    report = validate_rich_leaf_artifact(artifact)

    assert report.ok is False
    assert "artifact_self_declared_controlled_default" in report.blockers
    assert "rubric_link_copies_scoring_policy:rubric_link_1" in report.blockers
    assert report.canonical_truth_written is False
    assert report.official_score_allowed is False


def test_validator_rejects_missing_required_and_forbidden_truth_fields() -> None:
    empty = validate_rich_leaf_artifact({})
    assert empty.ok is False
    assert "artifact_missing_required:artifact_id" in empty.blockers
    assert "artifact_missing_required:source_refs" in empty.blockers

    artifact = _valid_artifact()
    artifact["canonical_truth_written"] = True
    artifact["official_score_allowed"] = True

    report = validate_rich_leaf_artifact(artifact)

    assert report.ok is False
    assert "artifact_forbidden_property:canonical_truth_written" in report.blockers
    assert "artifact_forbidden_property:official_score_allowed" in report.blockers


def test_validator_rejects_empty_source_span_even_with_matching_hash() -> None:
    artifact = _valid_artifact()
    artifact["source_refs"][0]["span"] = ""
    artifact["source_refs"][0]["span_hash"] = source_span_hash("")

    report = validate_rich_leaf_artifact(artifact)

    assert report.ok is False
    assert "source_ref_empty_span:src_1" in report.blockers
    assert "source_backed_field_without_valid_source:rules:rule_1" in report.blockers


def test_validator_requires_source_registry_for_source_backed_fields() -> None:
    artifact = _valid_artifact()
    artifact["source_refs"][0].pop("source_registry_id")

    report = validate_rich_leaf_artifact(artifact)

    assert report.ok is False
    assert "source_ref_missing_registry:src_1" in report.blockers
    assert "source_backed_field_without_valid_source:rules:rule_1" in report.blockers


def test_validator_keeps_council_shadow_candidate_only_not_learner_evidence() -> None:
    artifact = _valid_artifact()
    artifact["common_mistakes"]["observed_mistakes"].append(
        {
            "field_id": "mistake_bad",
            "claim_status": "learner_evidence",
            "observed_from": "council_shadow",
            "mistake_type": "vague_answer",
        }
    )

    report = validate_rich_leaf_artifact(artifact)

    assert report.ok is False
    assert "observed_mistake_from_non_authority:council_shadow:mistake_bad" in report.blockers


def test_pack_builder_strips_candidate_only_fields_and_records_consumption_trace() -> None:
    artifact = _valid_artifact()

    pack = build_compiled_context_pack(
        task="grading",
        artifacts=[artifact],
        bundle_version="v_rich_leaf_candidate_20260611",
        manifest_hash="sha256:test-manifest",
    )

    assert pack.task == "grading"
    assert pack.canonical_write_allowed is False
    assert pack.production_write_count == 0
    assert pack.consumption_trace["bundle_version"] == "v_rich_leaf_candidate_20260611"
    assert "rule_1" in pack.consumption_trace["consumed_field_ids"]
    assert "rubric_link_1" in pack.consumption_trace["consumed_field_ids"]
    assert "card_1" in pack.consumption_trace["stripped_candidate_field_ids"]
    assert "mistake_h1" in pack.consumption_trace["stripped_candidate_field_ids"]
    assert all(f.get("field_id") != "card_1" for f in pack.fields)


def test_review_pack_can_surface_candidate_negative_evidence_without_positive_runtime_use() -> None:
    artifact = {
        "artifact_id": "leaf_negative_evidence",
        "leaf_id": "L-negative",
        "bundle_version": "v_test",
        "candidate_status": "reviewed_candidate",
        "source_refs": [
            {
                "source_ref_id": "src_negative",
                "source_registry_id": "docs2026_registry",
                "source_dataset_id": "textbook_2026",
                "source_version": "2026.0",
                "extractor_version": "extractor.v1",
                "source_lane": "textbook",
                "path": "docs/2026/textbook.md",
                "record_id": "TB-negative",
                "span": "该段只说明父级路径，不说明当前 leaf 的具体术语。",
                "span_hash": source_span_hash("该段只说明父级路径，不说明当前 leaf 的具体术语。"),
            }
        ],
        "negative_evidence": [
            {
                "field_id": "neg_1",
                "claim_status": "candidate_only",
                "source_ref_ids": ["src_negative"],
                "negative_evidence_type": "wrong_leaf_source",
                "positive_context_allowed": False,
                "rationale": "semantic reviewer rejected this source for the leaf",
            }
        ],
    }

    grading_pack = build_compiled_context_pack(
        task="grading",
        artifacts=[artifact],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    review_pack = build_compiled_context_pack(
        task="review",
        artifacts=[artifact],
        bundle_version="v_test",
        manifest_hash="hash",
    )

    assert grading_pack.fields == []
    assert "neg_1" in grading_pack.consumption_trace["stripped_candidate_field_ids"]
    assert [field["field_id"] for field in review_pack.fields] == ["neg_1"]
    assert review_pack.fields[0]["claim_status"] == "candidate_only"
    assert review_pack.fields[0]["positive_context_allowed"] is False
    assert review_pack.consumption_trace["review_candidate_field_ids"] == ["neg_1"]
    assert [ref["source_ref_id"] for ref in review_pack.source_refs] == ["src_negative"]


def test_tutoring_pack_consumes_source_backed_concepts_without_grading_alias() -> None:
    artifact = _valid_artifact()

    pack = build_compiled_context_pack(
        task="tutoring",
        artifacts=[artifact],
        bundle_version="v_rich_leaf_candidate_20260611",
        manifest_hash="sha256:test-manifest",
    )

    consumed_ids = {field["field_id"] for field in pack.fields}
    assert "concept_1" in consumed_ids
    assert "rubric_link_1" not in consumed_ids
    assert "concept_1" in pack.consumption_trace["consumed_field_ids"]


def test_pack_builder_only_includes_source_refs_used_by_consumed_fields() -> None:
    artifact = {
        "artifact_id": "leaf_exam_pattern",
        "leaf_id": "L-question",
        "bundle_version": "v_test",
        "candidate_status": "reviewed_candidate",
        "source_refs": [
            {
                "source_ref_id": "src_question",
                "source_registry_id": "docs2026_registry",
                "source_dataset_id": "question_2026",
                "source_version": "2026.0",
                "extractor_version": "extractor.v1",
                "source_lane": "question",
                "path": "docs/2026/question.md",
                "record_id": "Q1",
                "span": "某真题考查建筑设计程序。",
                "span_hash": source_span_hash("某真题考查建筑设计程序。"),
            }
        ],
        "exam_patterns": [
            {
                "field_id": "exam_pattern_1",
                "claim_status": "assessment_evidence",
                "source_ref_ids": ["src_question"],
                "pattern_type": "question_lane_evidence",
                "knowledge_source_allowed": False,
            }
        ],
    }

    rag_pack = build_compiled_context_pack(
        task="rag_answer",
        artifacts=[artifact],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    next_action_pack = build_compiled_context_pack(
        task="next_action",
        artifacts=[artifact],
        bundle_version="v_test",
        manifest_hash="hash",
    )

    assert rag_pack.fields == []
    assert rag_pack.source_refs == []
    assert [field["field_id"] for field in next_action_pack.fields] == ["exam_pattern_1"]
    assert [ref["source_ref_id"] for ref in next_action_pack.source_refs] == ["src_question"]
