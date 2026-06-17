from __future__ import annotations

import json
from pathlib import Path


def _nearline_report() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_nearline_ab.v1",
        "verdict": "PASS",
        "verdict_ceiling": "NEARLINE_RETRIEVAL_PROJECTION",
        "quality_claim_allowed": False,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_nearline_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "eval_case_count": 50,
            "arm_count": 3,
            "blocker_count": 0,
            "current_rag_answerable_rate": 0.98,
            "current_rag_mean_token_proxy": 156.0,
            "treatment_answerable_rate": 1.0,
            "treatment_evidence_citation_rate": 1.0,
            "treatment_fail_open_rate": 0.0,
            "treatment_mean_token_proxy": 34.82,
            "treatment_token_proxy_delta_vs_current_rag": -121.18,
        },
        "effect_table": [
            {"arm": "baseline_empty_context", "fail_open_rate": 0.0},
            {"arm": "current_rag_lexical_retrieval", "fail_open_rate": 0.0},
            {
                "arm": "rich_leaf_promoted_context",
                "answerable_rate": 1.0,
                "evidence_citation_rate": 1.0,
                "fail_open_rate": 0.0,
                "question_lane_citation_rate": 0.0,
            },
        ],
        "not_exercised": [
            "production_rag_retrieval",
            "live_llm_semantic_judgment",
            "live_runtime_latency",
            "live_runtime_token_usage",
            "learner_outcome_gain",
            "production_default_decision",
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _field_promotion_review() -> dict:
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
            "promoted_artifact_candidate_count": 21,
            "source_backed_field_count": 84,
            "assessment_evidence_field_count": 9,
            "validation_failure_count": 0,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_live_ab_preflight_marks_ready_without_claiming_live_quality() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab_preflight import run_live_ab_preflight

    report = run_live_ab_preflight(
        field_promotion_review=_field_promotion_review(),
        nearline_ab=_nearline_report(),
    )

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1"
    assert report["verdict"] == "READY_FOR_LIVE_RUNTIME_AB"
    assert report["verdict_ceiling"] == "PREFLIGHT_ONLY"
    assert report["quality_claim_allowed"] is False
    assert report["summary"]["live_runtime_executed"] is False
    assert report["summary"]["provider_call_count"] == 0
    assert report["summary"]["blocker_count"] == 0
    assert report["execution_mode"] == "preflight_only"
    assert report["runtime_entry"]["runtime_exercised"] is False
    assert report["runtime_entry"]["entrypoint"] == "not_exercised"
    assert report["provider_call_policy"]["provider_call_count"] == 0
    assert report["source_bundle"]["nearline_verdict_ceiling"] == "NEARLINE_RETRIEVAL_PROJECTION"
    assert report["evidence_validation"]["question_lane_citation_rate"] == 0.0
    assert "runtime_not_exercised" in report["not_exercised_by_layer"]
    assert report["planned_arms"] == [
        "current_rag_runtime",
        "legacy_runtime_or_projection",
        "rich_leaf_promoted_context",
        "artifact_first_llm_judge",
    ]
    assert "production_rag_retrieval" in report["not_exercised"]
    assert "live_llm_semantic_judgment" in report["not_exercised"]
    assert report["classification"]["runtime_install_allowed"] is False


def test_live_ab_preflight_blocks_nearline_quality_claim() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab_preflight import run_live_ab_preflight

    nearline = _nearline_report()
    nearline["quality_claim_allowed"] = True

    report = run_live_ab_preflight(field_promotion_review=_field_promotion_review(), nearline_ab=nearline)

    assert report["verdict"] == "BLOCKED_FOR_LIVE_RUNTIME_AB"
    assert any("nearline_quality_claim_allowed" in blocker for blocker in report["blockers"])


def test_live_ab_preflight_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab_preflight import main

    field_promotion = tmp_path / "field_promotion_review.json"
    nearline = tmp_path / "semantic_runtime_nearline_ab.json"
    output = tmp_path / "live_ab_preflight.json"
    field_promotion.write_text(json.dumps(_field_promotion_review(), ensure_ascii=False), encoding="utf-8")
    nearline.write_text(json.dumps(_nearline_report(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--field-promotion-review",
            str(field_promotion),
            "--nearline-ab",
            str(nearline),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1"
    assert payload["verdict"] == "READY_FOR_LIVE_RUNTIME_AB"
