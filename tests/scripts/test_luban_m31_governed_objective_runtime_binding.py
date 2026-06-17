"""M31 runner test — hermetic end-to-end (Step 0 persist + route trace + safety + gating + go/no-go).

Runs the runner with --hermetic into TEMP tracked paths (never touches the real tracked bundle or the
real artifact dir). Asserts every hard gate passes and all safety invariants hold; hermetic coverage
yields WEAK-GO while the binding seam itself is fully proven.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from deeptutor.services.construction_grading import objective_runtime_adapter as A

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m31_runner", REPO / "scripts" / "run_luban_m31_governed_objective_runtime_binding.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


@pytest.fixture
def temp_paths(tmp_path, monkeypatch):
    gov = tmp_path / "gov"
    monkeypatch.setattr(A, "_GOVERNED_DIR", gov)
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", gov / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", gov / "canonical_pointer_m31.json")
    monkeypatch.setattr(runner, "OUT", tmp_path / "artifacts")
    monkeypatch.delenv("LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED", raising=False)
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()
    yield
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()


def test_runner_hermetic_all_gates_pass(temp_paths):
    result = runner.run(hermetic=True)
    go = result["go_no_go"]
    assert go["verdict"] in ("GO", "WEAK-GO")
    assert all(go["hard_gates"].values()), go["hard_gates"]
    assert go["verdict"] == "WEAK-GO"  # hermetic fixture coverage
    assert go["coverage"] == "hermetic_fixture"

    inv = result["safety_invariant_report"]
    assert inv["false_positive"] == 0
    assert inv["answer_key_override"] == 0
    assert inv["llm_changed_key"] == 0
    assert inv["rag_chunk_as_answer_key"] == 0
    assert inv["production_write_count"] == 0
    assert inv["canonical_truth_written"] is False
    assert inv["published"] is False
    assert inv["production_default_connected"] is False
    assert inv["tamper_fail_closed"] is True
    assert inv["client_supplied_registry_status_ignored"] is True
    assert inv["controlled_official_only"] is True
    assert inv["rejected_or_conflict_scored_as_release"] == 0
    assert inv["content_hash_reproducible"] is True

    route = result["route_trace"]
    assert route["hit"]["release_truth"] is True
    assert route["hit"]["controlled_official"] is True
    assert route["miss"]["official_score_allowed"] is not True

    gating = result["gating"]
    assert all(gating.values()), gating

    # artifacts written to the temp dir
    art = runner.OUT
    for f in ("go_no_go_m31.json", "safety_invariant_report_m31.json", "route_trace_m31.json",
              "canonical_pointer_m31.json", "FINDING_governed_objective_runtime_binding_m31_20260606.md"):
        assert (art / f).exists(), f
