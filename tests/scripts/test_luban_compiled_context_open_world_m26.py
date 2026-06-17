from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "run_luban_compiled_context_open_world_m26.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("m26_runner", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["m26_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load_module()


def test_open_world_lane_never_refuses_construction() -> None:
    rows = M.run_open_world_lane()
    construction = [r for r in rows if r["prompt"] != "<unsafe-control>"]
    assert construction
    assert all(r["is_construction_refusal"] is False for r in construction)
    assert all(r["status"] == "unverified_diagnostic" for r in construction)
    assert all(r["formal_score_allowed"] is False for r in construction)
    assert all(r["uncertainty_label"] for r in construction)


def test_objective_governed_signs_and_tamper_fails_closed() -> None:
    obj = M.run_objective_lanes()
    assert obj["governed_bundle_verified"] is True
    assert obj["governed_status"] == "release_candidate"
    assert obj["tamper_fail_closed"] is True
    assert obj["not_in_bank_payload"]["mode"] == "open_world_fail_open"


def test_consumer_ledger_three_surfaces_single_schema() -> None:
    consumer = M.run_consumer_ledger()
    assert consumer["single_schema"] is True
    assert len(consumer["surfaces"]) == 3
    assert consumer["learning_brain_preview_only"] is True


def test_compiler_feedback_blocks_laundering() -> None:
    rows = M.run_open_world_lane()
    entries = M.run_compiler_feedback(rows)
    rejected = [e for e in entries if e["kind"] == "rejected"]
    # rag_chunk + model_vote answer-key attempts must be rejected
    assert any("source_laundering_blocked" in e["reason"] for e in rejected)


def test_invariants_all_pass_and_go() -> None:
    rows = M.run_open_world_lane()
    obj = M.run_objective_lanes()
    consumer = M.run_consumer_ledger()
    entries = M.run_compiler_feedback(rows)
    lb = M.run_learning_brain(obj)
    inv = M.compute_invariants(rows, obj, consumer, entries, lb)
    assert inv["unknown_not_in_bank_refusal_rate"] == 0
    assert inv["canonical_truth_written"] is False
    assert inv["learning_brain_evidence_coverage"] >= 0.95
    assert inv["high_value_work_order_rate"] >= 0.9
    go = M.evaluate_go_no_go({**inv, "kbv5": M.kbv5_status()})
    assert go["verdict"] == "GO", go["failures"]


def test_main_writes_all_required_artifacts(tmp_path) -> None:
    rc = M.main.__wrapped__ if hasattr(M.main, "__wrapped__") else None
    # run main() into a temp dir via argv
    argv = sys.argv
    sys.argv = ["m26", "--out", str(tmp_path)]
    try:
        assert M.main() == 0
    finally:
        sys.argv = argv
    for name in M.REQUIRED_ARTIFACTS:
        assert (tmp_path / name).exists(), f"missing artifact {name}"
