import json
import os
import subprocess


SCRIPT = "scripts/run_luban_m35_scoring_artifact_ab.py"
REQUIRED_METRICS = {
    "compiled_hit_rate",
    "wrong_path_rate",
    "source_validity",
    "answer_improvement",
    "token_cost",
    "fail_open_rate",
    "point_precision",
    "point_recall",
    "score_mae",
}
REQUIRED_SAFETY = {
    "production_write_count": 0,
    "canonical_truth_written": False,
    "rag_chunk_as_answer_key": 0,
    "candidate_used_as_release_truth": 0,
    "client_status_promoted_to_release_truth": 0,
}


def _run_runner(tmp_path, tier: str, fixture_limit: int = 3) -> dict:
    out = tmp_path / f"m35_ab_{tier}.json"
    subprocess.run(
        [
            "python",
            SCRIPT,
            "--output",
            str(out),
            "--fixture-limit",
            str(fixture_limit),
            "--tier",
            tier,
        ],
        check=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_shape_stub_reports_shape_only_metrics_and_safety(tmp_path):
    payload = _run_runner(tmp_path, "shape_stub")

    assert payload["evaluation_tier"] == "shape_stub"
    assert payload["quality_claim_allowed"] is False
    assert payload["verdict_ceiling"] == "NO-GO_OR_SHAPE_ONLY"
    assert REQUIRED_METRICS <= set(payload["metrics"])
    for key, expected in REQUIRED_SAFETY.items():
        assert payload["safety"][key] == expected


def test_cached_judge_replay_keeps_generated_fixture_shape_only(tmp_path):
    payload = _run_runner(tmp_path, "cached_judge_replay")

    assert payload["evaluation_tier"] == "cached_judge_replay"
    assert payload["quality_claim_allowed"] is False
    assert payload["label_audit"]["verdict_ceiling"] == "SHAPE_ONLY"
    assert payload["label_audit"]["label_authority_counts"] == {
        "generated_self_label": 100
    }
    assert "prior_failure_comparison" in payload
    assert payload["prior_failure_comparison"][
        "old_human_vs_artifact_first_point_hit_agreement"
    ] == 0.5267
    assert payload["prior_failure_comparison"]["old_mean_abs_score_delta"] == 4.6091


def test_live_provider_sample_is_disabled_without_explicit_opt_in(tmp_path):
    env_keys = {
        "LUBAN_M35_ENABLE_LIVE_PROVIDER_SAMPLE",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
    }
    old_env = {key: os.environ.pop(key, None) for key in env_keys}
    try:
        payload = _run_runner(tmp_path, "live_provider_sample")
    finally:
        for key, value in old_env.items():
            if value is not None:
                os.environ[key] = value

    live = payload["arms"]["live_provider_sample"]
    assert live["status"] in {"not_exercised", "bounded_sample_disabled"}
    assert live["provider_called"] is False
    assert payload["safety"]["production_write_count"] == 0
    assert payload["safety"]["canonical_truth_written"] is False
