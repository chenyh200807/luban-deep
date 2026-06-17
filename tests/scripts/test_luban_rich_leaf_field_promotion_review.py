from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import (
    build_compiled_context_pack,
    source_span_hash,
    validate_rich_leaf_artifact,
)


def _source_ref(source_ref_id: str = "SRC1", lane: str = "textbook") -> dict:
    span = "建筑设计一般可分为四个阶段：方案设计、初步设计、技术设计和施工图设计。"
    return {
        "source_ref_id": source_ref_id,
        "source_registry_id": "rich_leaf_reviewed_source_refs",
        "source_dataset_id": f"docs2026_{lane}",
        "source_version": "2026.0",
        "extractor_version": "rich_leaf_field_candidate_compiler.v1",
        "source_lane": lane,
        "path": f"{lane}/source.json",
        "record_id": f"{lane.upper()}-1",
        "span": span,
        "span_hash": source_span_hash(span),
        "candidate_only": True,
        "review_only": True,
    }


def _artifact(*, lane: str = "textbook", family: str = "rules") -> dict:
    source_ref = _source_ref(lane=lane)
    artifact = {
        "artifact_id": f"A1:{family}",
        "leaf_id": "L1",
        "bundle_version": "v_test",
        "candidate_status": "reviewed_candidate",
        "source_refs": [source_ref],
        "definitions": [],
        "rules": [],
        "procedures": [],
        "numeric_constraints": [],
        "negative_evidence": [],
        "teaching_cards": [],
        "rubric_link_index": [],
        "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
        "exam_patterns": [],
        "learner_memory_event_templates": [],
    }
    base_field = {
        "field_id": f"F-{family}-{lane}",
        "claim_status": "candidate_only",
        "candidate_only": True,
        "review_only": True,
        "source_ref_ids": [source_ref["source_ref_id"]],
    }
    if family == "rules":
        artifact["rules"].append({**base_field, "statement": "建筑设计一般可分为四个阶段"})
    elif family == "concepts":
        artifact["concepts"] = [{**base_field, "concept_name": "建筑设计阶段", "aliases": ["方案设计"]}]
    elif family == "teaching_cards":
        artifact["teaching_cards"].append(
            {
                **base_field,
                "card": source_ref["span"],
                "source_excerpt": source_ref["span"],
                "not_for_official_scoring": True,
            }
        )
    elif family == "exam_patterns":
        artifact["exam_patterns"].append(
            {
                **base_field,
                "pattern_type": "question_lane_evidence",
                "knowledge_source_allowed": False,
            }
        )
    elif family == "learner_memory_event_templates":
        artifact["learner_memory_event_templates"].append(
            {
                **base_field,
                "event_type": "case_grading_completed",
                "template_status": "candidate_only_not_writeable",
                "canonical_write_allowed": False,
            }
        )
    elif family == "common_mistakes":
        artifact["common_mistakes"]["hypothesized_mistakes"].append(
            {
                **base_field,
                "observed_from": "synthetic_candidate",
                "mistake_type": "missing_or_confused_key_term",
                "learner_evidence_allowed": False,
            }
        )
    else:
        raise AssertionError(f"unsupported test family: {family}")
    return artifact


def _artifact_batch(*artifacts: dict) -> dict:
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
            "input_field_candidate_count": 1,
            "artifact_candidate_count": len(artifacts),
            "validation_failure_count": 0,
            "skipped_field_candidate_count": 0,
            "field_family_counts": {},
        },
        "rich_leaf_artifact_candidates": list(artifacts),
        "validation_reports": [],
        "skipped_field_candidates": [],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_field_promotion_review_promotes_source_backed_knowledge_fields() -> None:
    from scripts.run_luban_rich_leaf_field_promotion_review import review_field_promotions

    report = review_field_promotions(artifact_candidates=_artifact_batch(_artifact(family="rules")))

    assert report["schema"] == "luban_rich_leaf_field_promotion_review.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["summary"]["source_backed_field_count"] == 1
    promoted = report["promoted_rich_leaf_artifact_candidates"][0]
    assert promoted["rules"][0]["claim_status"] == "source_backed"
    assert promoted["rules"][0]["candidate_only"] is False
    assert validate_rich_leaf_artifact(promoted).ok is True

    pack = build_compiled_context_pack(
        task="rag_answer",
        artifacts=[promoted],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    assert [field["field_id"] for field in pack.fields] == ["F-rules-textbook"]


def test_field_promotion_review_promotes_concepts_but_keeps_memory_templates_candidate_only() -> None:
    from scripts.run_luban_rich_leaf_field_promotion_review import review_field_promotions

    report = review_field_promotions(
        artifact_candidates=_artifact_batch(
            _artifact(family="concepts"),
            _artifact(family="learner_memory_event_templates"),
        )
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["source_backed_field_count"] == 1
    assert report["summary"]["still_candidate_only_field_count"] == 1
    by_artifact = {artifact["artifact_id"]: artifact for artifact in report["promoted_rich_leaf_artifact_candidates"]}
    concept_artifact = by_artifact["A1:concepts"]
    template_artifact = by_artifact["A1:learner_memory_event_templates"]
    assert concept_artifact["concepts"][0]["claim_status"] == "source_backed"
    assert template_artifact["learner_memory_event_templates"][0]["claim_status"] == "candidate_only"

    next_action_pack = build_compiled_context_pack(
        task="next_action",
        artifacts=[template_artifact],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    assert next_action_pack.fields == []
    assert "F-learner_memory_event_templates-textbook" in next_action_pack.consumption_trace[
        "stripped_candidate_field_ids"
    ]


def test_field_promotion_review_keeps_hypothesized_common_mistakes_candidate_only() -> None:
    from scripts.run_luban_rich_leaf_field_promotion_review import review_field_promotions

    report = review_field_promotions(artifact_candidates=_artifact_batch(_artifact(family="common_mistakes")))

    assert report["verdict"] == "PASS"
    assert report["summary"]["still_candidate_only_field_count"] == 1
    promoted = report["promoted_rich_leaf_artifact_candidates"][0]
    mistake = promoted["common_mistakes"]["hypothesized_mistakes"][0]
    assert mistake["claim_status"] == "candidate_only"
    assert mistake["observed_from"] == "synthetic_candidate"

    next_action_pack = build_compiled_context_pack(
        task="next_action",
        artifacts=[promoted],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    assert next_action_pack.fields == []
    assert "F-common_mistakes-textbook" in next_action_pack.consumption_trace["stripped_candidate_field_ids"]


def test_field_promotion_review_keeps_question_lane_as_assessment_evidence_only() -> None:
    from scripts.run_luban_rich_leaf_field_promotion_review import review_field_promotions

    report = review_field_promotions(
        artifact_candidates=_artifact_batch(_artifact(lane="question", family="exam_patterns"))
    )

    promoted = report["promoted_rich_leaf_artifact_candidates"][0]
    assert promoted["exam_patterns"][0]["claim_status"] == "assessment_evidence"
    assert promoted["exam_patterns"][0]["knowledge_source_allowed"] is False
    assert report["summary"]["assessment_evidence_field_count"] == 1

    rag_pack = build_compiled_context_pack(
        task="rag_answer",
        artifacts=[promoted],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    next_action_pack = build_compiled_context_pack(
        task="next_action",
        artifacts=[promoted],
        bundle_version="v_test",
        manifest_hash="hash",
    )
    assert rag_pack.fields == []
    assert [field["field_id"] for field in next_action_pack.fields] == ["F-exam_patterns-question"]


def test_field_promotion_review_cli_writes_review_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_field_promotion_review import main

    candidates_path = tmp_path / "rich_leaf_artifact_candidates.json"
    output = tmp_path / "field_promotion_review.json"
    candidates_path.write_text(
        json.dumps(_artifact_batch(_artifact(family="teaching_cards")), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = main(["--artifact-candidates", str(candidates_path), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_field_promotion_review.v1"
    assert payload["summary"]["source_backed_field_count"] == 1
    assert payload["safety"]["installed_runtime_supply"] is False
