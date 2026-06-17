from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _live_ab_preflight() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1",
        "verdict": "READY_FOR_LIVE_RUNTIME_AB",
        "verdict_ceiling": "PREFLIGHT_ONLY",
        "quality_claim_allowed": False,
        "execution_mode": "preflight_only",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_live_ab_preflight": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "blocker_count": 0,
            "promoted_artifact_candidate_count": 20,
            "source_backed_field_count": 70,
            "nearline_eval_case_count": 50,
            "nearline_current_rag_answerable_rate": 0.94,
            "nearline_treatment_answerable_rate": 1.0,
            "nearline_treatment_fail_open_rate": 0.0,
            "nearline_treatment_token_proxy_delta_vs_current_rag": -418.78,
            "live_runtime_executed": False,
            "provider_call_count": 0,
        },
        "planned_arms": [
            "current_rag_runtime",
            "legacy_runtime_or_projection",
            "rich_leaf_promoted_context",
            "artifact_first_llm_judge",
        ],
        "not_exercised_by_layer": {
            "runtime_not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
            ],
            "release_not_exercised": ["production_default_decision", "release_truth_governance"],
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _authorized_live_results() -> dict:
    arms = [
        {
            "arm": "current_rag_runtime",
            "status": "completed",
            "sample_count": 5,
            "provider_call_count": 5,
            "answerable_rate": 0.8,
            "accuracy_rate": 0.8,
            "evidence_citation_rate": 0.8,
            "fail_open_rate": 0.0,
            "mean_token_usage": 1200,
            "mean_latency_ms": 900,
        },
        {
            "arm": "legacy_runtime_or_projection",
            "status": "completed",
            "sample_count": 5,
            "provider_call_count": 5,
            "answerable_rate": 0.8,
            "accuracy_rate": 0.8,
            "evidence_citation_rate": 0.6,
            "fail_open_rate": 0.0,
            "mean_token_usage": 900,
            "mean_latency_ms": 650,
        },
        {
            "arm": "rich_leaf_promoted_context",
            "status": "completed",
            "sample_count": 5,
            "provider_call_count": 5,
            "answerable_rate": 1.0,
            "accuracy_rate": 1.0,
            "evidence_citation_rate": 1.0,
            "fail_open_rate": 0.0,
            "mean_token_usage": 500,
            "mean_latency_ms": 500,
        },
        {
            "arm": "artifact_first_llm_judge",
            "status": "completed",
            "sample_count": 5,
            "provider_call_count": 5,
            "answerable_rate": 1.0,
            "accuracy_rate": 1.0,
            "evidence_citation_rate": 1.0,
            "fail_open_rate": 0.0,
            "mean_token_usage": 650,
            "mean_latency_ms": 620,
        },
    ]
    return {
        "schema": "luban_rich_leaf_semantic_runtime_live_ab_results.v1",
        "execution_authority": "authorized_live_runtime_trace",
        "runtime_entrypoint": "controlled_live_runtime_ab_runner",
        "runtime_exercised": True,
        "runtime_trace_ids": ["trace-live-001", "trace-live-002"],
        "provider_call_count": sum(arm["provider_call_count"] for arm in arms),
        "prompt_tokens": 9000,
        "completion_tokens": 2000,
        "total_tokens": 11000,
        "models": ["deepseek-chat"],
        "cost_recorded": True,
        "arms": arms,
    }


def test_live_ab_runner_blocks_provider_calls_by_default() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import run_live_ab

    report = run_live_ab(live_ab_preflight=_live_ab_preflight(), allow_provider_calls=False)

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_live_ab.v1"
    assert report["verdict"] == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED"
    assert report["verdict_ceiling"] == "LIVE_RUNTIME_NOT_EXERCISED"
    assert report["quality_claim_allowed"] is False
    assert report["execution_mode"] == "live_runtime_ab_blocked"
    assert report["summary"]["live_runtime_executed"] is False
    assert report["summary"]["provider_call_count"] == 0
    assert report["provider_call_policy"]["provider_calls_allowed"] is False
    assert report["runtime_entry"]["runtime_exercised"] is False
    assert report["classification"]["runtime_install_allowed"] is False
    assert "provider_authorization_missing" in report["blockers"]
    assert "production_rag_retrieval" in report["not_exercised_by_layer"]["runtime_not_exercised"]


def test_live_ab_runner_blocks_bad_preflight() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import run_live_ab

    preflight = _live_ab_preflight()
    preflight["quality_claim_allowed"] = True

    report = run_live_ab(live_ab_preflight=preflight, allow_provider_calls=False)

    assert report["verdict"] == "NO_GO_LIVE_PREFLIGHT_INVALID"
    assert any("preflight_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert report["quality_claim_allowed"] is False
    assert report["summary"]["provider_call_count"] == 0


def test_live_ab_runner_cli_writes_blocked_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import main

    preflight = tmp_path / "live_ab_preflight.json"
    output = tmp_path / "semantic_runtime_live_ab.json"
    _write_json(preflight, _live_ab_preflight())

    exit_code = main(["--live-ab-preflight", str(preflight), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_runtime_live_ab.v1"
    assert payload["verdict"] == "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED"
    assert payload["quality_claim_allowed"] is False


def test_live_ab_runner_accepts_authorized_live_trace_shadow_result() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import run_live_ab

    report = run_live_ab(
        live_ab_preflight=_live_ab_preflight(),
        allow_provider_calls=True,
        live_results=_authorized_live_results(),
    )

    assert report["verdict"] == "PASS_LIVE_RUNTIME_AB_SHADOW"
    assert report["verdict_ceiling"] == "LIVE_RUNTIME_SHADOW_ONLY"
    assert report["quality_claim_allowed"] is True
    assert report["quality_claim_scope"] == "live_shadow_only"
    assert report["summary"]["live_runtime_executed"] is True
    assert report["summary"]["live_case_count"] == 5
    assert report["summary"]["provider_call_count"] == 20
    assert report["provider_call_policy"]["provider_calls_allowed"] is True
    assert report["runtime_entry"]["runtime_exercised"] is True
    assert report["effect_table"][2]["arm"] == "rich_leaf_promoted_context"
    assert report["effect_table"][2]["accuracy_rate"] == 1.0
    assert report["classification"]["release_truth_claimed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_live_ab_runner_rejects_incomplete_or_fail_open_live_trace() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import run_live_ab

    live_results = _authorized_live_results()
    live_results["arms"] = live_results["arms"][:-1]
    live_results["arms"][0]["fail_open_rate"] = 0.2

    report = run_live_ab(
        live_ab_preflight=_live_ab_preflight(),
        allow_provider_calls=True,
        live_results=live_results,
    )

    assert report["verdict"] == "NO_GO_LIVE_RESULTS_INVALID"
    assert report["quality_claim_allowed"] is False
    assert any("live_results_missing_arm:artifact_first_llm_judge" in blocker for blocker in report["blockers"])
    assert any("live_results_arm_fail_open:current_rag_runtime" in blocker for blocker in report["blockers"])


def test_live_ab_runner_does_not_reward_cheap_abstention_as_token_win() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_ab import run_live_ab

    live_results = _authorized_live_results()
    for arm in live_results["arms"]:
        if arm["arm"] == "current_rag_runtime":
            arm["answerable_rate"] = 0.5
            arm["accuracy_rate"] = 0.99
            arm["mean_token_usage"] = 780
        if arm["arm"] == "rich_leaf_promoted_context":
            arm["answerable_rate"] = 1.0
            arm["accuracy_rate"] = 0.995
            arm["mean_token_usage"] = 840

    report = run_live_ab(
        live_ab_preflight=_live_ab_preflight(),
        allow_provider_calls=True,
        live_results=live_results,
    )

    assert report["verdict"] == "PASS_LIVE_RUNTIME_AB_SHADOW"
    by_arm = {row["arm"]: row for row in report["effect_table"]}
    assert by_arm["current_rag_runtime"]["mean_token_per_answerable"] == 1560.0
    assert by_arm["rich_leaf_promoted_context"]["mean_token_per_answerable"] == 840.0
