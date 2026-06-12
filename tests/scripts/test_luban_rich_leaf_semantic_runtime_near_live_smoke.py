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


def _field_promotion_review() -> dict:
    span = "建筑设计一般可分为四个阶段：方案设计、初步设计、技术设计和施工图设计。"
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
                "source_refs": [_source_ref("src_target", span)],
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


def _live_preflight() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1",
        "verdict": "READY_FOR_LIVE_RUNTIME_AB",
        "verdict_ceiling": "PREFLIGHT_ONLY",
        "quality_claim_allowed": False,
        "execution_mode": "preflight_only",
        "summary": {"blocker_count": 0, "provider_call_count": 0, "live_runtime_executed": False},
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_live_ab_preflight": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_near_live_smoke_exercises_local_runtime_adapter_without_quality_claim() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_smoke import run_near_live_smoke

    report = run_near_live_smoke(
        field_promotion_review=_field_promotion_review(),
        live_ab_preflight=_live_preflight(),
        limit=10,
    )

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_near_live_smoke.v1"
    assert report["verdict"] == "PASS"
    assert report["verdict_ceiling"] == "NEAR_LIVE_LOCAL_ADAPTER_ONLY"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "near_live_runtime"
    assert report["runtime_entry"]["entrypoint"] == "local_compiled_context_adapter"
    assert report["runtime_entry"]["runtime_exercised"] is True
    assert report["provider_call_policy"]["provider_call_count"] == 0
    assert report["summary"]["smoke_case_count"] == 1
    assert report["summary"]["answerable_rate"] == 1.0
    assert report["summary"]["evidence_citation_rate"] == 1.0
    assert report["summary"]["fail_open_rate"] == 0.0
    assert report["summary"]["question_lane_citation_rate"] == 0.0
    assert report["smoke_rows"][0]["runtime_answer"]["cited_source_ref_ids"] == ["src_target"]
    assert "production_rag_retrieval" in report["not_exercised_by_layer"]["runtime_not_exercised"]


def test_near_live_smoke_blocks_preflight_not_ready() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_smoke import run_near_live_smoke

    preflight = _live_preflight()
    preflight["verdict"] = "BLOCKED_FOR_LIVE_RUNTIME_AB"

    report = run_near_live_smoke(
        field_promotion_review=_field_promotion_review(),
        live_ab_preflight=preflight,
    )

    assert report["verdict"] == "FAIL"
    assert any("live_ab_preflight_not_ready" in blocker for blocker in report["blockers"])


def test_near_live_smoke_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_smoke import main

    field_promotion = tmp_path / "field_promotion_review.json"
    preflight = tmp_path / "live_ab_preflight.json"
    output = tmp_path / "near_live_smoke.json"
    field_promotion.write_text(json.dumps(_field_promotion_review(), ensure_ascii=False), encoding="utf-8")
    preflight.write_text(json.dumps(_live_preflight(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--field-promotion-review",
            str(field_promotion),
            "--live-ab-preflight",
            str(preflight),
            "--output",
            str(output),
            "--limit",
            "10",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_near_live_smoke.v1"
    assert payload["runtime_entry"]["runtime_exercised"] is True
