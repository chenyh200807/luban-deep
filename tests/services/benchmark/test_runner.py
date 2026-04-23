from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from deeptutor.services.benchmark.runner import run_benchmark, write_benchmark_artifacts


@pytest.mark.asyncio
async def test_run_benchmark_uses_registry_suites_and_reuses_arr_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_semantic_router_suite():
        return (
            {
                "suite": "semantic-router",
                "total_cases": 2,
                "passed": 1,
                "failed": 1,
                "skipped": 0,
                "pass_rate": 0.5,
                "failure_taxonomy": [{"failure_type": "FAIL_ROUTE_WRONG", "count": 1}],
                "case_tiers": {"gate_stable": 2},
            },
            [
                {
                    "suite": "semantic-router",
                    "case_id": "semantic_case_a",
                    "case_name": "semantic_case_a",
                    "status": "PASS",
                    "case_tier": "gate_stable",
                    "failure_type": None,
                    "evidence": {"route": "correct"},
                    "latency_ms": 10.0,
                    "details": {},
                },
                {
                    "suite": "semantic-router",
                    "case_id": "semantic_case_b",
                    "case_name": "semantic_case_b",
                    "status": "FAIL",
                    "case_tier": "gate_stable",
                    "failure_type": "FAIL_ROUTE_WRONG",
                    "evidence": {"route": "wrong"},
                    "latency_ms": 11.0,
                    "details": {},
                },
            ],
        )

    def fake_run_context_orchestration_suite():
        return (
            {
                "suite": "context-orchestration",
                "total_cases": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "pass_rate": 1.0,
                "failure_taxonomy": [],
                "case_tiers": {"gate_stable": 1},
            },
            [
                {
                    "suite": "context-orchestration",
                    "case_id": "context_case_a",
                    "case_name": "context_case_a",
                    "status": "PASS",
                    "case_tier": "gate_stable",
                    "failure_type": None,
                    "evidence": {"route": "correct"},
                    "latency_ms": 12.0,
                    "details": {},
                }
            ],
        )

    def fake_run_rag_grounding_suite():
        return (
            {
                "suite": "rag-grounding",
                "total_cases": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "pass_rate": 1.0,
                "failure_taxonomy": [],
                "case_tiers": {"regression_tier": 1},
            },
            [
                {
                    "suite": "rag-grounding",
                    "case_id": "rag_case_a",
                    "case_name": "rag_case_a",
                    "status": "PASS",
                    "case_tier": "regression_tier",
                    "failure_type": None,
                    "evidence": {"grounding": "correct"},
                    "latency_ms": 13.0,
                    "details": {},
                }
            ],
        )

    async def fake_run_local_long_dialog_suite():
        return (
            {
                "suite": "long-dialog-focus",
                "total_cases": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "pass_rate": 1.0,
                "failure_taxonomy": [],
                "case_tiers": {"regression_tier": 1},
            },
            [
                {
                    "suite": "long-dialog-focus",
                    "case_id": "ld_case_a",
                    "case_name": "ld_case_a",
                    "status": "PASS",
                    "case_tier": "regression_tier",
                    "failure_type": None,
                    "evidence": {"continuity": "ok"},
                    "latency_ms": 14.0,
                    "details": {"artifact_path": "tmp/ld.json"},
                }
            ],
        )

    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_semantic_router_suite",
        fake_run_semantic_router_suite,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_context_orchestration_suite",
        fake_run_context_orchestration_suite,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_rag_grounding_suite",
        fake_run_rag_grounding_suite,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_local_long_dialog_suite",
        fake_run_local_long_dialog_suite,
    )

    payload = await run_benchmark()

    assert payload["run_manifest"]["requested_suites"] == [
        "pr_gate_core",
        "regression_watch",
        "incident_replay",
        "exploration_lab",
    ]
    assert [item["suite"] for item in payload["suite_summaries"]] == [
        "pr_gate_core",
        "regression_watch",
        "incident_replay",
        "exploration_lab",
    ]
    assert payload["run_manifest"]["registry_version"] == "phase1"
    assert payload["release_spine"]
    assert payload["summary"]["passed"] == 4
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["skipped"] == 2
    assert payload["failure_taxonomy"] == [{"failure_type": "FAIL_ROUTE_WRONG", "count": 1}]
    assert payload["baseline_diff"] is None
    assert payload["runtime_evidence_links"] == [
        {"suite": "incident_replay", "case_id": "ld_case_a", "artifact_path": "tmp/ld.json"}
    ]
    wx_case = next(
        item for item in payload["case_results"] if item["case_id"] == "surface.wx.renderer.parity"
    )
    assert wx_case["status"] == "SKIP"
    assert wx_case["evidence"]["reason"] == "unsupported_surface_parity_eval"
    assert any(item["suite"] == "exploration_lab" for item in payload["blind_spots"])
    assert any(item["case_id"] == "surface.wx.renderer.parity" for item in payload["blind_spots"])
    assert any(item["case_id"] == "surface.web.ack.smoke" for item in payload["blind_spots"])
    assert all("source_suite" in item for item in payload["case_results"])
    assert payload["legacy"]["suite_summaries"][0]["suite"] == "semantic-router"
    assert payload["legacy"]["case_results"][0]["suite"] == "semantic-router"


@pytest.mark.asyncio
async def test_run_benchmark_computes_canonical_baseline_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_semantic_router_suite():
        return (
            {"suite": "semantic-router", "total_cases": 1, "passed": 0, "failed": 1, "skipped": 0, "pass_rate": 0.0},
            [
                {
                    "suite": "semantic-router",
                    "case_id": "semantic_case_a",
                    "case_name": "semantic_case_a",
                    "status": "FAIL",
                    "case_tier": "gate_stable",
                    "failure_type": "FAIL_ROUTE_WRONG",
                    "evidence": {},
                    "latency_ms": None,
                    "details": {},
                }
            ],
        )

    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_semantic_router_suite",
        fake_run_semantic_router_suite,
    )
    baseline = {
        "run_manifest": {"run_id": "benchmark-prev"},
        "summary": {"pass_rate": 1.0},
        "case_results": [
            {"suite": "pr_gate_core", "case_id": "semantic_case_a", "status": "PASS"}
        ],
    }

    payload = await run_benchmark(suite_names=("pr_gate_core",), baseline_payload=baseline)

    assert payload["baseline_diff"]["pass_rate_delta"] < 0
    assert payload["baseline_diff"]["regressions"] == [
        {"case_key": "pr_gate_core::semantic_case_a", "failure_type": "FAIL_ROUTE_WRONG"}
    ]


@pytest.mark.asyncio
async def test_run_benchmark_live_lite_defaults_long_dialog_to_one_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_long_dialog_suite(**kwargs):
        captured.update(kwargs)
        return (
            {"suite": "long-dialog-focus", "total_cases": 1, "passed": 1, "failed": 0, "skipped": 0, "pass_rate": 1.0},
            [
                {
                    "suite": "long-dialog-focus",
                    "case_id": "ld_case_a",
                    "case_name": "ld_case_a",
                    "status": "PASS",
                    "case_tier": "regression_tier",
                    "failure_type": None,
                    "evidence": {},
                    "latency_ms": None,
                    "details": {},
                }
            ],
        )

    def fake_surface_ack_smoke(**kwargs):
        return {
            "surface": "web",
            "passed": True,
            "missing_requirements": [],
            "metrics_url": "http://example.test/metrics",
            "session_id": "s",
            "turn_id": "t",
        }

    monkeypatch.setattr(
        "deeptutor.services.observability.arr_runner.run_long_dialog_suite",
        fake_run_long_dialog_suite,
    )
    monkeypatch.setattr(
        "deeptutor.services.observability.surface_ack_smoke.run_surface_ack_smoke",
        fake_surface_ack_smoke,
    )

    await run_benchmark(suite_names=("incident_replay",), api_base_url="http://example.test")

    assert captured["mode"] == "lite"
    assert captured["max_cases"] == 1


def test_write_benchmark_artifacts_writes_json_and_markdown(tmp_path: Path) -> None:
    payload = {
        "run_manifest": {
            "run_id": "benchmark-1",
            "generated_at": "2026-04-23 12:00:00",
            "registry_version": "phase1",
            "dataset_id": "benchmark_phase1",
            "requested_suites": ["pr_gate_core"],
        },
        "release_spine": {"release_id": "rel-1"},
        "suite_summaries": [],
        "case_results": [],
        "failure_taxonomy": [],
        "summary": {"total_cases": 0, "executed_cases": 0, "passed": 0, "failed": 0, "skipped": 0, "pass_rate": None},
        "baseline_diff": None,
        "runtime_evidence_links": [],
        "blind_spots": [],
        "legacy": {},
    }

    paths = write_benchmark_artifacts(payload, output_dir=tmp_path)

    json_path = Path(paths["json_path"])
    md_path = Path(paths["md_path"])
    assert json_path.exists()
    assert md_path.exists()
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["run_manifest"]["run_id"] == "benchmark-1"


def test_run_benchmark_cli_writes_artifacts(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_benchmark.py",
            "--suite",
            "exploration_lab",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Benchmark 完成" in completed.stdout
    assert list(tmp_path.glob("benchmark_run_*.json"))
    assert list(tmp_path.glob("benchmark_run_*.md"))


def test_run_benchmark_cli_accepts_positional_suite(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_benchmark.py",
            "exploration_lab",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Suites: exploration_lab" in completed.stdout
