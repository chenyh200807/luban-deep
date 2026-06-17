"""M31: governed objective runtime binding (fat skill).

Exercises the REAL governed loader gates (verify_lane_bundle + pinned content_hash + status gate +
namespace pin) end-to-end by writing a signed bundle + canonical pointer to a temp dir and pointing
the adapter's tracked-path constants at it. Hermetic (no live DB, no network).

A governed hit scores in-bank objective answers as CONTROLLED release-truth; a miss / tamper / pinned
hash mismatch / published status / namespace mismatch all fall THROUGH to the candidate -> open-world
lane and NEVER mint release-truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.construction_grading import full_knowledge_compiler as fkc
from deeptutor.services.construction_grading import objective_runtime_adapter as A
from deeptutor.services.construction_grading.compiled_context import (
    build_pack_from_question_context,
)

_ROWS = [
    {"question_id": "GOV_SC_1", "question_type": "single_choice",
     "stem": "临时用电应采用几级配电？",
     "options": {"A": "三级", "B": "两级", "C": "一级", "D": "四级"}, "official_answer": "A"},
    {"question_id": "GOV_MC_1", "question_type": "multi_choice",
     "stem": "专项方案应含哪些？",
     "options": {"A": "依据", "B": "概况", "C": "计划", "D": "无关"}, "official_answer": "ABC"},
    {"question_id": "GOV_TF_1", "question_type": "judgment",
     "stem": "深基坑监测属危大工程。", "options": {"A": "对", "B": "错"}, "official_answer": "对"},
]


def _write_bundle(dir_path: Path, *, bundle: dict, expected_hash: str, coverage: str = "hermetic_test") -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "objective_answer_key_release_candidate_m31.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    pointer = {"namespace": "objective_answer_key_full", "status": "release_candidate",
               "published": False, "expected_content_hash": expected_hash, "coverage": coverage}
    (dir_path / "canonical_pointer_m31.json").write_text(json.dumps(pointer), "utf-8")


@pytest.fixture
def governed(tmp_path, monkeypatch):
    """Install a valid signed governed bundle at a temp tracked path and return its index keys."""
    bundle = fkc.compile_full_objective_release_candidate(_ROWS)
    _write_bundle(tmp_path, bundle=bundle, expected_hash=bundle["manifest"]["content_hash"])
    monkeypatch.setattr(A, "_GOVERNED_DIR", tmp_path)
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "canonical_pointer_m31.json")
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()
    yield {"bundle": bundle, "dir": tmp_path}
    A._governed_index.cache_clear()
    A._candidate_index.cache_clear()


def test_governed_hit_is_controlled_release_truth(governed):
    p = A.build_governed_objective_payload(question_id="GOV_SC_1", selected_option="A")
    assert p["mode"] == "governed_objective_release_candidate"
    assert p["status"] == "release_candidate"
    assert p["release_truth"] is True
    assert p["official_score_allowed"] is True
    assert p["controlled_official"] is True
    assert p["result"]["is_correct"] is True
    assert p["llm_may_decide_correctness"] is False
    assert p["not_production_grade"] is False
    assert p["writeback_performed"] is False
    assert p["authority"] == "luban_grading_engine_m31_governed_objective"


def test_governed_multi_choice_order_independent(governed):
    correct = A.build_governed_objective_payload(question_id="GOV_MC_1", selected_option="CBA")
    assert correct["result"]["is_correct"] is True  # ABC order-independent
    assert correct["release_truth"] is True
    partial = A.build_governed_objective_payload(question_id="GOV_MC_1", selected_option="AB")
    assert partial["result"]["is_correct"] is False  # missing C
    assert partial["release_truth"] is True  # still governed authority, just wrong answer


def test_governed_wrong_answer_is_release_truth_but_incorrect(governed):
    p = A.build_governed_objective_payload(question_id="GOV_SC_1", selected_option="B")
    assert p["release_truth"] is True
    assert p["result"]["is_correct"] is False  # answer_key authority unchanged


def test_not_in_bank_falls_through_no_release_truth(governed):
    p = A.build_governed_objective_payload(question_id="NOT_IN_ANY_BANK_xyz", selected_option="A")
    assert p["mode"] != "governed_objective_release_candidate"
    assert p.get("release_truth") is not True
    assert p.get("official_score_allowed") is not True


def test_tamper_on_disk_fails_through(governed):
    # mutate the persisted bundle's answer_key WITHOUT re-signing -> loader must reject.
    bundle_path = governed["dir"] / "objective_answer_key_release_candidate_m31.json"
    bundle = json.loads(bundle_path.read_text("utf-8"))
    bundle["records"][0]["answer_key"] = "ZZZ"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    A._governed_index.cache_clear()
    verified, _index, reason = A._governed_index()
    assert verified is False
    assert reason == "verify_lane_bundle_failed"
    p = A.build_governed_objective_payload(question_id="GOV_SC_1", selected_option="A")
    assert p["mode"] != "governed_objective_release_candidate"  # fell through, not officially scored


def test_pinned_hash_mismatch_rejected(tmp_path, monkeypatch):
    bundle = fkc.compile_full_objective_release_candidate(_ROWS)
    _write_bundle(tmp_path, bundle=bundle, expected_hash="deadbeef_wrong_hash")  # pointer lies
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "canonical_pointer_m31.json")
    A._governed_index.cache_clear()
    verified, _index, reason = A._governed_index()
    assert verified is False
    assert reason == "pinned_hash_mismatch"


def test_published_status_rejected(tmp_path, monkeypatch):
    bundle = fkc.compile_full_objective_release_candidate(_ROWS)
    bundle["manifest"]["published"] = True  # never trust a published bundle at runtime
    _write_bundle(tmp_path, bundle=bundle, expected_hash=bundle["manifest"]["content_hash"])
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "canonical_pointer_m31.json")
    A._governed_index.cache_clear()
    verified, _index, reason = A._governed_index()
    assert verified is False
    # published flips verify_lane_bundle's signature (status is part of the signature) first.
    assert reason in ("verify_lane_bundle_failed", "status_gate_failed")


def test_namespace_mismatch_rejected(tmp_path, monkeypatch):
    bundle = fkc.compile_full_objective_release_candidate(_ROWS)
    bundle["manifest"]["namespace"] = "objective_answer_key_governed"  # different lane
    _write_bundle(tmp_path, bundle=bundle, expected_hash=bundle["manifest"]["content_hash"])
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "objective_answer_key_release_candidate_m31.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "canonical_pointer_m31.json")
    A._governed_index.cache_clear()
    verified, _index, reason = A._governed_index()
    assert verified is False  # signature is over (hash|namespace|status); swapped namespace fails
    assert reason == "namespace_mismatch"


def test_client_injected_registry_status_cannot_flip_official():
    # F1: a context-supplied registry_status is ignored; only the trusted kwarg grants authority.
    pack = build_pack_from_question_context(
        {"question_id": "x", "registry_status": "published", "answer_key": "A", "status": "resolved"},
        governed_registry_status="",
    )
    assert pack.official_score_allowed is False


def test_absent_bundle_falls_through(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_GOVERNED_BUNDLE", tmp_path / "missing.json")
    monkeypatch.setattr(A, "_GOVERNED_POINTER", tmp_path / "missing_pointer.json")
    A._governed_index.cache_clear()
    verified, _index, reason = A._governed_index()
    assert verified is False and reason == "absent"
    p = A.build_governed_objective_payload(question_id="GOV_SC_1", selected_option="A")
    assert p["mode"] != "governed_objective_release_candidate"
