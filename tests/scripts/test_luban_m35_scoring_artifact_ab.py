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


def test_quality_claim_requires_computed_quality_metrics(tmp_path):
    import json as _json

    from scripts.run_luban_m35_scoring_artifact_ab import build_report

    answers = tmp_path / "student_answers.jsonl"
    answers.write_text(
        _json.dumps(
            {
                "answer_id": "A1",
                "question_id": "Q1-NA",
                "student_answer": "需要组织专家论证",
                "gold_score": 2,
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "label_authority": "teacher_validated",
                "label_scope": "point_and_score",
                "sample_bucket": "hit",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(_json.dumps({"fixture_id": "m35_test"}), encoding="utf-8")

    report = build_report(
        tier="cached_judge_replay",
        answers_path=answers,
        manifest_path=manifest,
        fixture_limit=1,
        allow_live_provider_sample=False,
    )
    # Labels allow quality, but no quality metric was actually computed:
    # the runner must NOT mark quality as claimable.
    assert report["metrics"]["point_precision"] is None
    assert report["quality_claim_allowed"] is False


def test_fastapi_manifest_scoring_points_are_used_as_artifacts(tmp_path):
    import json as _json

    from scripts.run_luban_m35_scoring_artifact_ab import build_report

    answers = tmp_path / "student_answers.jsonl"
    answers.write_text(
        _json.dumps(
            {
                "answer_id": "A1",
                "question_id": "Q2023-01__P01",
                "student_answer": "由见证人员记录取样和现场检测情况。",
                "label_authority": "estimated_metadata_only",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        _json.dumps(
            {
                "fixture_id": "fastapi_case_subquestions",
                "questions": [
                    {
                        "question_id": "Q2023-01__P01",
                        "scoring_points": [
                            {
                                "point_id": "Q2023-01__P01::SP01",
                                "criterion": "应由见证人员记录其取样、现场检测情况。",
                                "source_refs": [
                                    {
                                        "source_type": "exam_reference_answer",
                                        "verified": True,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_report(
        tier="cached_judge_replay",
        answers_path=answers,
        manifest_path=manifest,
        fixture_limit=0,
        allow_live_provider_sample=False,
    )

    assert report["metrics"]["compiled_hit_rate"] == 1.0
    assert report["metrics"]["wrong_path_rate"] == 0.0
    assert report["metrics"]["source_validity"] == 1.0
    assert report["artifact_first"]["artifact_available_count"] == 1
