from __future__ import annotations

import asyncio
import json

import pytest

from deeptutor.services.observability import reset_control_plane_store
from deeptutor.services.observability.arr_runner import (
    _map_long_dialog_failure,
    assess_long_dialog_readiness,
    build_arr_report_payload,
    compute_baseline_diff,
    load_arr_baseline_payload,
    resolve_long_dialog_source_path,
    run_local_long_dialog_suite,
    run_context_orchestration_suite,
    run_rag_grounding_suite,
    run_semantic_router_suite,
    write_arr_artifacts,
)


@pytest.mark.asyncio
async def test_semantic_router_suite_returns_passing_fixture_results() -> None:
    suite_summary, case_results = await run_semantic_router_suite()

    assert suite_summary["suite"] == "semantic-router"
    assert suite_summary["failed"] == 0
    assert suite_summary["passed"] == len(case_results)
    assert all(item["status"] == "PASS" for item in case_results)


def test_context_orchestration_suite_returns_passing_fixture_results() -> None:
    suite_summary, case_results = run_context_orchestration_suite()

    assert suite_summary["suite"] == "context-orchestration"
    assert suite_summary["failed"] == 0
    assert suite_summary["passed"] == len(case_results)
    assert all(item["status"] == "PASS" for item in case_results)


def test_rag_grounding_suite_returns_passing_fixture_results() -> None:
    suite_summary, case_results = run_rag_grounding_suite()

    assert suite_summary["suite"] == "rag-grounding"
    assert suite_summary["failed"] == 0
    assert suite_summary["passed"] == len(case_results)
    assert all(item["status"] == "PASS" for item in case_results)
    assert all(item["case_tier"] == "gate_stable" for item in case_results)


@pytest.mark.asyncio
async def test_local_long_dialog_suite_returns_passing_fixture_results() -> None:
    suite_summary, case_results = await run_local_long_dialog_suite()

    assert suite_summary["suite"] == "long-dialog-focus"
    assert suite_summary["failed"] == 0
    assert suite_summary["passed"] == len(case_results)
    assert all(item["status"] == "PASS" for item in case_results)
    assert all(item["case_tier"] == "regression_tier" for item in case_results)


def test_map_long_dialog_failure_treats_anchor_miss_as_product_behavior() -> None:
    assert (
        _map_long_dialog_failure(
            {
                "summary": {
                    "hard_errors": 0,
                    "followup_object_mismatch_count": 0,
                    "anchor_miss_count": 1,
                    "context_reset_count": 0,
                    "slow_turns": 0,
                    "question_count_mismatch_count": 0,
                    "compare_table_miss_count": 0,
                    "stale_replay_count": 0,
                }
            }
        )
        == "FAIL_PRODUCT_BEHAVIOR"
    )


def test_map_long_dialog_failure_keeps_context_reset_as_context_loss() -> None:
    assert (
        _map_long_dialog_failure(
            {
                "summary": {
                    "hard_errors": 0,
                    "followup_object_mismatch_count": 0,
                    "anchor_miss_count": 0,
                    "context_reset_count": 1,
                    "slow_turns": 0,
                    "question_count_mismatch_count": 0,
                    "compare_table_miss_count": 0,
                    "stale_replay_count": 0,
                }
            }
        )
        == "FAIL_CONTEXT_LOSS"
    )


def test_compute_baseline_diff_detects_regressions_new_failures_and_recoveries() -> None:
    baseline_payload = {
        "run_id": "arr-lite-old",
        "summary": {"pass_rate": 1.0},
        "case_results": [
            {"suite": "semantic-router", "case_id": "case_a", "status": "PASS"},
            {"suite": "context-orchestration", "case_id": "case_b", "status": "FAIL"},
        ],
    }
    current_payload = {
        "run_id": "arr-lite-new",
        "summary": {"pass_rate": 0.5},
        "case_results": [
            {
                "suite": "semantic-router",
                "case_id": "case_a",
                "status": "FAIL",
                "failure_type": "FAIL_ROUTE_WRONG",
            },
            {"suite": "context-orchestration", "case_id": "case_b", "status": "PASS"},
            {
                "suite": "long-dialog-focus",
                "case_id": "case_c",
                "status": "FAIL",
                "failure_type": "FAIL_CONTINUITY",
            },
        ],
    }

    diff = compute_baseline_diff(
        baseline_payload=baseline_payload,
        current_payload=current_payload,
    )

    assert diff is not None
    assert diff["pass_rate_delta"] == -0.5
    assert diff["regressions"] == [
        {
            "case_key": "semantic-router::case_a",
            "failure_type": "FAIL_ROUTE_WRONG",
        }
    ]
    assert diff["new_failures"] == [
        {
            "case_key": "long-dialog-focus::case_c",
            "failure_type": "FAIL_CONTINUITY",
        }
    ]
    assert diff["recovered"] == [{"case_key": "context-orchestration::case_b"}]


def test_assess_long_dialog_readiness_requires_source_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPTUTOR_OPENAI_API_KEY", raising=False)

    readiness = assess_long_dialog_readiness("/definitely/missing/source.json")

    assert readiness["ready"] is False
    assert "missing_source_json" in readiness["reasons"]
    assert "missing_openai_api_key" in readiness["reasons"]


def test_assess_long_dialog_readiness_with_api_base_url_skips_openai_key_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPTUTOR_OPENAI_API_KEY", raising=False)

    readiness = assess_long_dialog_readiness(
        "/definitely/missing/source.json",
        api_base_url="http://127.0.0.1:8001",
    )

    assert readiness["ready"] is False
    assert "missing_source_json" in readiness["reasons"]
    assert "missing_openai_api_key" not in readiness["reasons"]


def test_resolve_long_dialog_source_path_finds_fastapi_artifact_from_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parent = tmp_path / "repos"
    main_repo = parent / "deeptutor"
    worktree = parent / "deeptutor-worktrees" / "observability-m0-m1"
    legacy_repo = parent / "FastAPI20251222"
    artifact = legacy_repo / "artifacts" / "long_dialog_round7_full_detail_20260328.json"
    main_repo.mkdir(parents=True)
    worktree.mkdir(parents=True)
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    (worktree / ".git").write_text(
        f"gitdir: {main_repo / '.git' / 'worktrees' / 'observability-m0-m1'}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.PROJECT_ROOT",
        worktree,
    )

    resolved = resolve_long_dialog_source_path()

    assert resolved == artifact


@pytest.mark.asyncio
async def test_run_long_dialog_suite_passes_api_base_url_to_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    output_dir = tmp_path / "arr"
    output_dir.mkdir(parents=True)
    source_path = tmp_path / "source.json"
    source_path.write_text("{}", encoding="utf-8")
    artifact_dir = output_dir / "long_dialog_123"
    artifact_dir.mkdir(parents=True)
    artifact_path = artifact_dir / "long_dialog_v1_retest_smart_20260419_000000.json"
    artifact_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "LD_001",
                    "title": "demo",
                    "summary": {
                        "hard_errors": 0,
                        "followup_object_mismatch_count": 0,
                        "anchor_miss_count": 0,
                        "context_reset_count": 0,
                        "slow_turns": 0,
                        "question_count_mismatch_count": 0,
                        "compare_table_miss_count": 0,
                        "stale_replay_count": 0,
                        "semantic_score": 96,
                        "satisfaction_score": 95,
                        "avg_latency_ms": 1234.5,
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.assess_long_dialog_readiness",
        lambda explicit_path=None, api_base_url=None: {
            "ready": True,
            "source_path": str(source_path),
            "python_executable": "python3.11",
            "reasons": [],
            "api_base_url": api_base_url,
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.time.time",
        lambda: 123.0,
    )

    def fake_run(command, cwd, capture_output, text, check):
        captured["command"] = command
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("deeptutor.services.observability.arr_runner.subprocess.run", fake_run)

    from deeptutor.services.observability.arr_runner import run_long_dialog_suite

    suite_summary, results = await run_long_dialog_suite(
        mode="full",
        explicit_source_json=str(source_path),
        output_dir=output_dir,
        api_base_url="http://127.0.0.1:8001",
        response_mode="deep",
    )

    assert suite_summary["passed"] == 1
    assert results[0]["status"] == "PASS"
    assert "--api-base-url" in captured["command"]
    assert "http://127.0.0.1:8001" in captured["command"]
    assert "--response-mode" in captured["command"]
    assert "deep" in captured["command"]


def test_load_arr_baseline_payload_falls_back_to_latest_control_plane_run(tmp_path) -> None:
    reset_control_plane_store(base_dir=tmp_path / "control_plane")
    from deeptutor.services.observability import get_control_plane_store

    previous = {
        "run_id": "arr-lite-prev",
        "summary": {"pass_rate": 0.9},
        "case_results": [{"suite": "semantic-router", "case_id": "case_a", "status": "PASS"}],
    }
    get_control_plane_store().write_run(
        kind="arr_runs",
        run_id="arr-lite-prev",
        release_id="rel-prev",
        payload=previous,
    )

    loaded = load_arr_baseline_payload(None)

    assert loaded == previous


def test_build_arr_report_payload_returns_rich_analysis_sections() -> None:
    payload = {
        "run_id": "arr-lite-demo",
        "generated_at": "2026-04-19 18:30:00",
        "mode": "lite",
        "release": {"release_id": "rel-1"},
        "suite_summaries": [
            {
                "suite": "semantic-router",
                "total_cases": 2,
                "passed": 1,
                "failed": 1,
                "skipped": 0,
                "pass_rate": 0.5,
                "failure_taxonomy": [{"failure_type": "FAIL_ROUTE_WRONG", "count": 1}],
                "case_tiers": {"gate_stable": 2},
            }
        ],
        "case_results": [
            {
                "suite": "semantic-router",
                "case_id": "case_a",
                "case_name": "case_a",
                "status": "PASS",
                "case_tier": "gate_stable",
                "failure_type": None,
                "evidence": {"expected": "x"},
                "latency_ms": 10.0,
                "details": {},
            },
            {
                "suite": "semantic-router",
                "case_id": "case_b",
                "case_name": "case_b",
                "status": "FAIL",
                "case_tier": "gate_stable",
                "failure_type": "FAIL_ROUTE_WRONG",
                "evidence": {"expected": "y", "actual": "z"},
                "latency_ms": 30.0,
                "details": {},
            },
        ],
        "summary": {
            "total_cases": 2,
            "executed_cases": 2,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "pass_rate": 0.5,
            "case_tiers": {"gate_stable": 2},
            "gate_stable_pass_rate": 0.5,
            "regression_tier_failed": 0,
            "failure_taxonomy": [{"failure_type": "FAIL_ROUTE_WRONG", "count": 1}],
        },
        "baseline_diff": {
            "baseline_run_id": "arr-lite-prev",
            "pass_rate_delta": -0.5,
            "regressions": [{"case_key": "semantic-router::case_b", "failure_type": "FAIL_ROUTE_WRONG"}],
            "new_failures": [],
            "recovered": [],
        },
        "gate_summary": {
            "bootstrap_mode": True,
            "gate_stable_pass_rate": 0.5,
            "regression_tier_failed": 0,
            "new_regressions": 1,
        },
    }

    report = build_arr_report_payload(payload)

    assert report["run_summary"]["run_id"] == "arr-lite-demo"
    assert report["run_summary"]["pass_rate_pct"] == 50.0
    assert report["latency_summary"]["avg_latency_ms"] == 20.0
    assert report["failure_type_distribution"] == [
        {"name": "FAIL_ROUTE_WRONG", "count": 1, "pct": 50.0}
    ]
    assert report["failures"][0]["case_key"] == "semantic-router::case_b"
    assert report["failures"][0]["reason"]
    assert report["failures"][0]["remediation"]
    assert report["failures"][0]["confidence"] == 0.9
    assert report["baseline_diff"]["baseline_run_id"] == "arr-lite-prev"
    assert report["report_limitations"]


def test_write_arr_artifacts_writes_html_and_analysis_json(tmp_path) -> None:
    payload = {
        "run_id": "arr-lite-demo",
        "generated_at": "2026-04-19 18:30:00",
        "mode": "lite",
        "release": {"release_id": "rel-1"},
        "suite_summaries": [],
        "case_results": [],
        "summary": {
            "total_cases": 0,
            "executed_cases": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "pass_rate": None,
            "case_tiers": {},
            "gate_stable_pass_rate": None,
            "regression_tier_failed": 0,
            "failure_taxonomy": [],
        },
        "baseline_diff": None,
        "gate_summary": {
            "bootstrap_mode": True,
            "gate_stable_pass_rate": None,
            "regression_tier_failed": 0,
            "new_regressions": 0,
        },
    }

    paths = write_arr_artifacts(payload, output_dir=tmp_path)

    assert paths["html_path"].endswith(".html")
    assert paths["analysis_json_path"].endswith(".json")
    html_path = tmp_path / paths["html_path"].split("/")[-1]
    analysis_path = tmp_path / paths["analysis_json_path"].split("/")[-1]
    assert html_path.exists()
    assert analysis_path.exists()
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert analysis["run_summary"]["run_id"] == "arr-lite-demo"
