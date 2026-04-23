from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.benchmark import BenchmarkRegistry
from deeptutor.services.benchmark.registry import (
    dump_benchmark_registry,
    load_benchmark_registry,
)


def _load_registry() -> BenchmarkRegistry:
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_phase1_registry.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return BenchmarkRegistry.from_dict(payload)


def test_registry_uses_version_and_cases_mapping() -> None:
    registry = _load_registry()

    assert registry.version == "phase1"
    assert registry.dataset_id == "benchmark_phase1"
    assert registry.dataset_version == "phase1.0"
    assert not isinstance(registry.cases, dict)
    assert not isinstance(registry.suites, dict)
    with pytest.raises(TypeError):
        registry.cases["new_case"] = registry.cases["routing.semantic_router.case_set"]  # type: ignore[index]
    assert len(registry.cases) == 6
    assert set(registry.suites) == {
        "pr_gate_core",
        "regression_watch",
        "incident_replay",
        "exploration_lab",
    }


def test_semantic_case_uses_canonical_vocab() -> None:
    registry = _load_registry()
    case = registry.cases["routing.semantic_router.case_set"]

    assert case.dataset_id == "benchmark_phase1"
    assert case.dataset_version == "phase1.0"
    assert case.case_id == "routing.semantic_router.case_set"
    assert case.contract_domain == "routing_contract"
    assert case.case_tier == "gate_stable"
    assert case.execution_kind == "static_contract_eval"
    assert case.surface == "backend"
    assert case.source_fixture == "tests/fixtures/semantic_router_eval_cases.json"
    assert case.failure_taxonomy_scope == ("FAIL_ROUTE_WRONG",)
    assert case.expected_contract


def test_context_orchestration_case_uses_canonical_vocab() -> None:
    registry = _load_registry()
    case = registry.cases["routing.context_orchestration.case_set"]

    assert case.dataset_id == "benchmark_phase1"
    assert case.dataset_version == "phase1.0"
    assert case.case_id == "routing.context_orchestration.case_set"
    assert case.contract_domain == "continuity_contract"
    assert case.case_tier == "gate_stable"
    assert case.execution_kind == "static_contract_eval"
    assert case.surface == "backend"
    assert case.source_fixture == "tests/fixtures/context_orchestration_eval_cases.json"
    assert case.failure_taxonomy_scope == ("FAIL_CONTEXT_LOSS",)
    assert case.expected_contract


def test_grounding_case_uses_canonical_vocab() -> None:
    registry = _load_registry()
    case = registry.cases["grounding.rag.case_set"]

    assert case.dataset_id == "benchmark_phase1"
    assert case.dataset_version == "phase1.0"
    assert case.case_id == "grounding.rag.case_set"
    assert case.contract_domain == "grounding_contract"
    assert case.case_tier == "regression_tier"
    assert case.execution_kind == "static_contract_eval"
    assert case.surface == "backend"
    assert case.source_fixture == "tests/fixtures/rag_grounding_eval_cases.json"
    assert case.failure_taxonomy_scope == ("FAIL_GROUNDEDNESS",)
    assert case.expected_contract


def test_long_dialog_case_uses_canonical_vocab() -> None:
    registry = _load_registry()
    case = registry.cases["continuity.long_dialog.focus"]

    assert case.dataset_id == "benchmark_phase1"
    assert case.dataset_version == "phase1.0"
    assert case.case_id == "continuity.long_dialog.focus"
    assert case.contract_domain == "continuity_contract"
    assert case.case_tier == "incident_replay"
    assert case.execution_kind == "live_ws_replay"
    assert case.surface == "backend"
    assert case.source_fixture == "tests/fixtures/long_dialog_focus_eval_cases.json"
    assert case.failure_taxonomy_scope == ("FAIL_CONTINUITY",)
    assert case.expected_contract


def test_wx_and_web_surface_cases_use_canonical_vocab() -> None:
    registry = _load_registry()
    wx_case = registry.cases["surface.wx.renderer.parity"]
    web_case = registry.cases["surface.web.ack.smoke"]

    assert wx_case.case_id == "surface.wx.renderer.parity"
    assert wx_case.contract_domain == "surface_contract"
    assert wx_case.case_tier == "exploratory"
    assert wx_case.execution_kind == "surface_parity_eval"
    assert wx_case.surface == "wx_miniprogram"
    assert wx_case.source_fixture == "tests/fixtures/wechat_structured_renderer_cases.json"
    assert wx_case.failure_taxonomy_scope == ("FAIL_SURFACE_DELIVERY",)
    assert wx_case.expected_contract

    assert web_case.case_id == "surface.web.ack.smoke"
    assert web_case.contract_domain == "production_replay_contract"
    assert web_case.case_tier == "incident_replay"
    assert web_case.execution_kind == "live_ws_replay"
    assert web_case.surface == "web"
    assert web_case.source_fixture == "scripts/run_surface_ack_smoke.py"
    assert web_case.failure_taxonomy_scope == ("FAIL_SURFACE_DELIVERY",)
    assert web_case.expected_contract


def test_all_case_ids_exist() -> None:
    registry = _load_registry()

    assert set(registry.cases) == {
        "routing.semantic_router.case_set",
        "routing.context_orchestration.case_set",
        "grounding.rag.case_set",
        "continuity.long_dialog.focus",
        "surface.wx.renderer.parity",
        "surface.web.ack.smoke",
    }


def test_loader_rejects_missing_or_empty_case_ids() -> None:
    with pytest.raises(ValueError, match="case_ids must not be missing"):
        BenchmarkRegistry.from_dict(
            {
                "version": "phase1",
                "dataset_id": "benchmark_phase1",
                "dataset_version": "phase1.0",
                "cases": {},
                "suites": {"broken_suite": {}},
            }
        )

    with pytest.raises(ValueError, match="case_ids must not be empty"):
        BenchmarkRegistry.from_dict(
            {
                "version": "phase1",
                "dataset_id": "benchmark_phase1",
                "dataset_version": "phase1.0",
                "cases": {},
                "suites": {"broken_suite": {"case_ids": []}},
            }
        )


def test_dump_and_load_round_trip_preserves_key_fields(tmp_path: Path) -> None:
    source_path = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_phase1_registry.json"
    original = load_benchmark_registry(source_path)
    payload = dump_benchmark_registry(original)

    round_trip_path = tmp_path / "benchmark_phase1_registry_round_trip.json"
    round_trip_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    reloaded = load_benchmark_registry(round_trip_path)

    assert reloaded.version == original.version
    assert reloaded.dataset_id == original.dataset_id
    assert reloaded.dataset_version == original.dataset_version
    assert set(reloaded.cases) == set(original.cases)
    assert set(reloaded.suites) == set(original.suites)
    assert reloaded.cases["routing.semantic_router.case_set"].expected_contract == (
        original.cases["routing.semantic_router.case_set"].expected_contract
    )
    assert reloaded.cases["surface.web.ack.smoke"].source_fixture == (
        original.cases["surface.web.ack.smoke"].source_fixture
    )
