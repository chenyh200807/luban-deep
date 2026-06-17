from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.rich_leaf_artifacts import validate_rich_leaf_artifact


def _field_candidate(family: str = "rules", lane: str = "textbook") -> dict:
    payload = {
        "field_candidate_id": f"FC-{family}-{lane}",
        "family": family,
        "leaf_id": "L1",
        "artifact_id": "A1",
        "derived_from_candidate_id": "RC1",
        "audit_item_id": "audit:1",
        "claim_status": "candidate_only",
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "source_ref_trace": {
            "source_lane": lane,
            "source_path": f"{lane}/source.json",
            "record_id": f"{lane.upper()}-1",
            "span": "根据基础深度宜分段分层（300～500mm）连续浇筑混凝土，一般不留施工缝。",
            "span_hash": "will_be_recomputed",
            "matched_terms": ["混凝土"],
        },
    }
    if family == "rules":
        payload["rule_text"] = "宜分段分层连续浇筑混凝土"
    elif family == "concepts":
        payload["concept_name"] = "混凝土"
        payload["aliases"] = ["浇筑混凝土"]
    elif family == "numeric_constraints":
        payload["items"] = [{"value": "300～500mm", "context": "分段分层（300～500mm）连续浇筑"}]
    elif family == "exam_patterns":
        payload["pattern_type"] = "question_lane_evidence"
        payload["knowledge_source_allowed"] = False
    elif family == "learner_memory_event_templates":
        payload["event_type"] = "case_grading_completed"
        payload["template_status"] = "candidate_only_not_writeable"
        payload["canonical_write_allowed"] = False
    elif family == "common_mistakes":
        payload["mistake_group"] = "hypothesized_mistakes"
        payload["observed_from"] = "synthetic_candidate"
        payload["mistake_type"] = "missing_or_confused_key_term"
        payload["learner_evidence_allowed"] = False
    return payload


def _field_batch(*candidates: dict) -> dict:
    return {
        "schema": "luban_rich_leaf_field_candidate_batch.v1",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "rich_field_candidate_batch": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "reviewed_candidate_count": len(candidates),
            "generated_field_candidate_count": len(candidates),
            "source_backed_knowledge_candidate_count": len(
                [c for c in candidates if c["source_ref_trace"]["source_lane"] != "question"]
            ),
            "question_lane_exam_pattern_count": len([c for c in candidates if c["family"] == "exam_patterns"]),
            "skipped_candidate_count": 0,
            "field_family_counts": {},
        },
        "field_candidates": list(candidates),
        "skipped_candidates": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_artifact_candidate_assembler_builds_validator_clean_candidate_artifact() -> None:
    from scripts.run_luban_rich_leaf_artifact_candidate_assembler import assemble_artifact_candidates

    report = assemble_artifact_candidates(
        field_candidates=_field_batch(_field_candidate("rules"), _field_candidate("numeric_constraints"))
    )

    assert report["schema"] == "luban_rich_leaf_artifact_candidate_batch.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["summary"]["artifact_candidate_count"] == 1
    assert report["summary"]["field_family_counts"]["rules"] == 1
    assert report["summary"]["field_family_counts"]["numeric_constraints"] == 1
    artifact = report["rich_leaf_artifact_candidates"][0]
    validation = validate_rich_leaf_artifact(artifact)
    assert validation.ok is True
    assert artifact["candidate_status"] == "reviewed_candidate"
    assert artifact["source_refs"][0]["source_registry_id"] == "rich_leaf_reviewed_source_refs"
    assert artifact["rules"][0]["field_id"] == "FC-rules-textbook"
    assert artifact["rules"][0]["source_ref_ids"] == [artifact["source_refs"][0]["source_ref_id"]]
    assert artifact["numeric_constraints"][0]["claim_status"] == "candidate_only"


def test_artifact_candidate_assembler_keeps_concepts_and_templates_validator_clean() -> None:
    from scripts.run_luban_rich_leaf_artifact_candidate_assembler import assemble_artifact_candidates

    report = assemble_artifact_candidates(
        field_candidates=_field_batch(
            _field_candidate("concepts"),
            _field_candidate("learner_memory_event_templates"),
        )
    )

    assert report["verdict"] == "PASS"
    artifact = report["rich_leaf_artifact_candidates"][0]
    assert artifact["concepts"][0]["field_id"] == "FC-concepts-textbook"
    assert artifact["concepts"][0]["concept_name"] == "混凝土"
    assert artifact["learner_memory_event_templates"][0]["canonical_write_allowed"] is False
    assert validate_rich_leaf_artifact(artifact).ok is True


def test_artifact_candidate_assembler_places_common_mistakes_in_hypothesis_bucket() -> None:
    from scripts.run_luban_rich_leaf_artifact_candidate_assembler import assemble_artifact_candidates

    report = assemble_artifact_candidates(field_candidates=_field_batch(_field_candidate("common_mistakes")))

    assert report["verdict"] == "PASS"
    assert report["summary"]["field_family_counts"]["common_mistakes"] == 1
    artifact = report["rich_leaf_artifact_candidates"][0]
    assert artifact["common_mistakes"]["observed_mistakes"] == []
    mistake = artifact["common_mistakes"]["hypothesized_mistakes"][0]
    assert mistake["field_id"] == "FC-common_mistakes-textbook"
    assert mistake["observed_from"] == "synthetic_candidate"
    assert mistake["claim_status"] == "candidate_only"
    assert validate_rich_leaf_artifact(artifact).ok is True


def test_artifact_candidate_assembler_keeps_question_lane_in_exam_patterns_only() -> None:
    from scripts.run_luban_rich_leaf_artifact_candidate_assembler import assemble_artifact_candidates

    report = assemble_artifact_candidates(field_candidates=_field_batch(_field_candidate("exam_patterns", "question")))

    artifact = report["rich_leaf_artifact_candidates"][0]
    assert artifact["rules"] == []
    assert artifact["exam_patterns"][0]["field_id"] == "FC-exam_patterns-question"
    assert artifact["exam_patterns"][0]["knowledge_source_allowed"] is False
    assert validate_rich_leaf_artifact(artifact).ok is True


def test_artifact_candidate_assembler_cli_writes_artifact_batch(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_artifact_candidate_assembler import main

    field_candidates = tmp_path / "rich_leaf_field_candidates.json"
    out_dir = tmp_path / "out"
    field_candidates.write_text(json.dumps(_field_batch(_field_candidate("rules")), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--field-candidates", str(field_candidates), "--output-dir", str(out_dir)])

    assert exit_code == 0
    payload = json.loads((out_dir / "rich_leaf_artifact_candidates.json").read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_artifact_candidate_batch.v1"
    assert payload["safety"]["installed_runtime_supply"] is False
