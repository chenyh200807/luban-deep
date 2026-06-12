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
                "source_refs": [_source_ref("src_target", span), _source_ref("src_noise", "施工现场临时用电应符合安全管理要求。")],
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


def _near_live_smoke() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_near_live_smoke.v1",
        "verdict": "PASS",
        "verdict_ceiling": "NEAR_LIVE_LOCAL_ADAPTER_ONLY",
        "quality_claim_allowed": False,
        "execution_mode": "near_live_runtime",
        "summary": {
            "blocker_count": 0,
            "smoke_case_count": 1,
            "answerable_rate": 1.0,
            "evidence_citation_rate": 1.0,
            "fail_open_rate": 0.0,
            "question_lane_citation_rate": 0.0,
            "provider_call_count": 0,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_near_live_smoke": True,
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


def test_near_live_shadow_ab_compares_local_adapter_against_rag_proxy() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab import run_near_live_shadow_ab

    report = run_near_live_shadow_ab(
        field_promotion_review=_field_promotion_review(),
        near_live_smoke=_near_live_smoke(),
        limit=50,
        top_k=2,
    )

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1"
    assert report["verdict"] == "PASS"
    assert report["verdict_ceiling"] == "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "near_live_shadow"
    assert report["summary"]["shadow_case_count"] == 1
    assert report["summary"]["provider_call_count"] == 0
    assert report["summary"]["local_adapter_fail_open_rate"] == 0.0
    by_arm = {row["arm"]: row for row in report["effect_table"]}
    assert by_arm["current_rag_lexical_proxy"]["answerable_rate"] == 1.0
    assert by_arm["rich_leaf_local_adapter"]["answerable_rate"] == 1.0
    assert by_arm["rich_leaf_local_adapter"]["mean_token_proxy"] < by_arm["current_rag_lexical_proxy"]["mean_token_proxy"]
    assert "production_rag_retrieval" in report["not_exercised_by_layer"]["runtime_not_exercised"]


def test_near_live_shadow_ab_local_adapter_rows_keep_traceable_evidence() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab import run_near_live_shadow_ab

    report = run_near_live_shadow_ab(
        field_promotion_review=_field_promotion_review(),
        near_live_smoke=_near_live_smoke(),
        limit=50,
        top_k=2,
    )

    adapter_rows = report["local_adapter_rows"]
    assert adapter_rows
    row = adapter_rows[0]
    assert row["artifact_id"] == "A1"
    assert row["leaf_id"] == "L1"
    assert row["field_id"] == "rule_1"
    assert row["family"] == "rules"
    assert row["cited_source_ref_ids"] == ["src_target"]
    assert row["expected_source_ref_ids"] == ["src_target"]
    assert row["answer"]["cited_source_ref_ids"] == ["src_target"]
    assert row["answer"]["text"] == "建筑设计一般可分为四个阶段"


def test_near_live_shadow_ab_keeps_full_current_rag_rows_for_live_trace() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab import run_near_live_shadow_ab

    report = run_near_live_shadow_ab(
        field_promotion_review=_field_promotion_review(),
        near_live_smoke=_near_live_smoke(),
        limit=50,
        top_k=2,
    )

    assert report["current_rag_rows"]
    assert len(report["current_rag_rows"]) == report["summary"]["shadow_case_count"]
    assert report["current_rag_rows"][0]["arm"] == "current_rag_lexical_proxy"
    assert report["sample_rows"]


def test_near_live_shadow_ab_blocks_failed_smoke() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab import run_near_live_shadow_ab

    smoke = _near_live_smoke()
    smoke["verdict"] = "FAIL"

    report = run_near_live_shadow_ab(field_promotion_review=_field_promotion_review(), near_live_smoke=smoke)

    assert report["verdict"] == "FAIL"
    assert any("near_live_smoke_not_pass" in blocker for blocker in report["blockers"])


def test_near_live_shadow_ab_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab import main

    field_promotion = tmp_path / "field_promotion_review.json"
    smoke = tmp_path / "near_live_smoke.json"
    output = tmp_path / "near_live_shadow_ab.json"
    field_promotion.write_text(json.dumps(_field_promotion_review(), ensure_ascii=False), encoding="utf-8")
    smoke.write_text(json.dumps(_near_live_smoke(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--field-promotion-review",
            str(field_promotion),
            "--near-live-smoke",
            str(smoke),
            "--output",
            str(output),
            "--limit",
            "50",
            "--top-k",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1"
    assert payload["classification"]["runtime_install_allowed"] is False
