"""Textbook verbatim lane runner — end-to-end on REAL 2026 textbook blocks (hermetic --no-llm).

Runs the compiler over a bounded slice of the real textbook into TEMP paths (never pollutes the
tracked supply or artifact dir). Asserts every signed point is provably verbatim, all safety gates
hold, and the runtime hand-off authority is the server kwarg only. Skips if the textbook is absent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "textbook_compile_runner", REPO / "scripts" / "run_luban_textbook_knowledge_compile.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

pytestmark = pytest.mark.skipif(
    not runner.BOOK_DIR.exists(), reason="2026 textbook source not present in this checkout")


@pytest.fixture
def temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OUT", tmp_path / "artifacts")
    monkeypatch.setattr(runner, "SUPPLY_DIR", tmp_path / "supply")
    yield


def test_runner_signs_only_verbatim_and_all_gates_hold(temp_paths):
    out = runner.run(live=False, limit=40)
    go = out["go_no_go"]
    assert go["verdict"] in ("GO", "WEAK-GO")        # WEAK-GO at limit<600 blocks
    assert all(go["hard_gates"].values()), go["hard_gates"]
    assert out["coverage"]["signed_count"] > 0
    assert out["coverage"]["dropped_count"] == 0

    # independent provenance audit: EVERY signed point is verbatim in its block's corpus
    assert out["audit"]["verbatim_rate_ok"] is True
    assert out["audit"]["quote_not_in_corpus"] == 0
    assert out["audit"]["key_number_not_in_corpus"] == 0

    # runtime hand-off: authority is the server kwarg, never the bundle
    assert out["handoff"]["authority_is_server_kwarg_only"] is True

    # tracked supply + ledgers written to temp paths
    assert (runner.SUPPLY_DIR / "textbook_knowledge_release_candidate.json").exists()
    assert (runner.SUPPLY_DIR / "canonical_pointer.json").exists()
    for f in ("coverage_report.json", "verbatim_audit.json", "work_order_backlog.jsonl",
              "go_no_go.json", "FINDING_textbook_knowledge_full.md"):
        assert (runner.OUT / f).exists(), f


def test_bundle_verifies_and_published_false(temp_paths):
    out = runner.run(live=False, limit=40)
    from deeptutor.services.construction_grading import compiled_registry_resolver as RES
    sup = RES.load_supply(runner.SUPPLY_DIR, bundle_name="textbook_knowledge_release_candidate.json")
    assert sup is not None
    bundle, pointer = sup
    from deeptutor.services.construction_grading import full_knowledge_compiler as FKC
    assert FKC.verify_lane_bundle(bundle, "textbook_knowledge_full") is True
    assert bundle["manifest"]["published"] is False
    # node-indexed: a real signed node resolves; tamper fails closed
    node = next(iter(bundle["manifest"]["node_index"]))
    assert RES.resolve_node(node, bundle=bundle, pointer=pointer) is not None
    bundle["records"][0]["textbook_quote"] = "篡改"
    assert RES.resolve_node(node, bundle=bundle, pointer=pointer) is None
