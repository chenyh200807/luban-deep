"""Living LLM Artifact Compiler — first vertical slice runner (end-to-end, hermetic --no-llm).

Runs the slice runner into TEMP output/supply paths (never pollutes the tracked supply or the real
artifact dir). Asserts the whole loop is GO on real M2 evidence: signs machine_spec points, the
bundle verifies, runtime hand-off authority is the server kwarg only, every safety gate holds.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "compiler_slice_runner", REPO / "scripts" / "run_luban_compiler_pipeline_slice.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

pytestmark = pytest.mark.skipif(
    not runner.M2_DIR.exists(),
    reason="M2 machine_spec audit packets are not tracked in this checkout",
)


@pytest.fixture
def temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OUT", tmp_path / "artifacts")
    monkeypatch.setattr(runner, "SUPPLY_DIR", tmp_path / "supply")
    yield


def test_slice_runner_go_on_real_m2_evidence(temp_paths):
    out = runner.run(no_llm=True)
    go = out["go_no_go"]
    assert go["verdict"] == "GO", go
    assert all(go["hard_gates"].values()), go["hard_gates"]
    assert out["m2_count"] > 0  # real M2 machine_spec points were ingested

    bundle = out["result1"]["signed_bundle"]
    assert bundle is not None
    from deeptutor.services.construction_grading import full_knowledge_compiler as FKC
    assert FKC.verify_lane_bundle(bundle, "case_rubric_full") is True
    assert bundle["manifest"]["published"] is False

    # runtime hand-off: authority is the server kwarg, never the bundle
    assert out["handoff"]["authority_is_server_kwarg_only"] is True
    assert out["handoff"]["granted_official_score_allowed"] is True
    assert out["handoff"]["ungranted_official_score_allowed"] is False

    # safety invariants
    s = out["result1"]["safety"]
    assert s["candidate_used_as_release_truth"] == 0
    assert s["illegit_promote_outside_s5"] == 0
    assert s["production_write_count"] == 0
    assert s["canonical_truth_written"] is False
    assert s["tamper_fail_closed"] is True

    # M20 delta absorbed through the previously-dead executor (no promotion to release truth)
    assert out["m20"]["candidate_used_as_release_truth"] == 0

    # tracked supply persisted + ledger emitted into temp paths
    assert (runner.SUPPLY_DIR / "case_rubric_release_candidate_slice.json").exists()
    assert (runner.SUPPLY_DIR / "canonical_pointer.json").exists()
    for f in ("go_no_go.json", "pipeline_safety_report.json", "runtime_handoff_proof.json",
              "loop_reingest_proof.json", "FINDING_living_compiler_slice.md"):
        assert (runner.OUT / f).exists(), f
