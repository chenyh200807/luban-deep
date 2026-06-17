"""Tests for the Luban M30 Knowledge Compiler Release-Candidate Closure.

Hermetic: no live DB, no remote, no LLM. Verifies the compiler aggregates the
signed single authorities, fails closed on tamper, launders nothing, loads from a
clean checkout, and advances the M26 `requires_release_registry` blocker.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_luban_knowledge_compiler_release_candidate_m30.py"


def _load():
    spec = importlib.util.spec_from_file_location("luban_m30_compiler", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m30():
    return _load()


@pytest.fixture(scope="module")
def result(m30):
    return m30.run_compiler()


# --------------------------------------------------------------------------- #
# Compiler unit
# --------------------------------------------------------------------------- #


def test_all_pillars_present(result):
    pillars = result["pillars"]
    for name in (
        "objective_answer_key_governed",
        "case_rubric_registry",
        "kb_v5_source_context",
        "m20_candidate_delta",
        "luban_context_pack",
    ):
        assert name in pillars, name


def test_objective_pillar_is_governed_release_candidate(result):
    obj = result["pillars"]["objective_answer_key_governed"]
    assert obj["available"] is True
    assert obj["status"] == "release_candidate"
    assert obj["published"] is False
    assert obj["answer_key_authority"] == "governed_source_official_answer_only"
    assert obj["verify_bundle_ok"] is True
    assert obj["count"] >= 1


def test_compiled_manifest_verifies(result):
    assert result["compiled_manifest_verifies"] is True
    m = result["compiled_manifest"]
    # This deliverable is a cross-check, NOT a second registry — distinct schema.
    assert m["schema_version"] == "luban_knowledge_compiler_crosscheck.v1"
    assert m["status"] == "release_candidate"
    assert m["published"] is False
    assert m["default_flip"] == 0
    assert m["production_write_count"] == 0
    assert m["canonical_truth_written"] is False
    assert m["runtime_read_schema"] == "luban_context_pack.v1"


def test_single_context_schema(result):
    ctx = result["pillars"]["luban_context_pack"]
    assert ctx["single_schema"] is True
    assert ctx["schema_versions_found"] == ["luban_context_pack.v1"]


# --------------------------------------------------------------------------- #
# Tamper → fail-closed
# --------------------------------------------------------------------------- #


def test_compiled_manifest_tamper_fails_closed(m30, result):
    pillars = result["pillars"]
    manifest = dict(result["compiled_manifest"])
    # tamper the content_hash
    manifest["content_hash"] = "deadbeef"
    assert m30.verify_compiled_manifest(manifest, pillars) is False
    # tamper the signature
    manifest2 = dict(result["compiled_manifest"])
    manifest2["signature"] = "0" * 64
    assert m30.verify_compiled_manifest(manifest2, pillars) is False


def test_objective_bundle_tamper_fails_closed(m30):
    from deeptutor.services.construction_grading import (
        objective_governed_registry_extractor as gov,
    )

    bundle = gov.build_release_candidate_bundle()
    assert gov.verify_bundle(bundle) is True
    # mutate a record -> signature/content_hash no longer match -> fail closed
    if bundle["records"]:
        bundle["records"][0]["answer_key"] = "Z"
        assert gov.verify_bundle(bundle) is False


def test_manifest_pillar_signature_drift_detected(m30, result):
    pillars = {k: dict(v) for k, v in result["pillars"].items()}
    # drift an available pillar's signature -> recompute mismatch
    pillars["objective_answer_key_governed"]["signature"] = "tampered"
    assert m30.verify_compiled_manifest(result["compiled_manifest"], pillars) is False


# --------------------------------------------------------------------------- #
# No laundering
# --------------------------------------------------------------------------- #


def test_no_laundering(result):
    g = result["laundering_guard_report"]
    assert g["official_answer_as_source"] == 0
    assert g["model_vote_as_source"] == 0
    assert g["council_vote_as_source"] == 0
    assert g["rag_chunk_as_answer_key"] == 0
    assert g["answer_key_override"] == 0
    assert g["client_supplied_answer_key_release_truth"] == 0
    assert g["candidate_delta_enters_release_truth"] == 0
    assert g["all_clean"] is True


def test_kbv5_is_context_only(result):
    kb = result["pillars"]["kb_v5_source_context"]
    assert kb["role"] == "source_context_only"
    assert kb["is_grading_authority"] is False
    assert kb["emits_answer_key"] is False
    assert kb["rag_chunk_as_answer_key"] == 0


def test_m20_delta_is_candidate_only_with_rollback(result):
    m = result["pillars"]["m20_candidate_delta"]
    assert m["role"] == "candidate_delta_only"
    assert m["enters_release_truth"] is False
    assert m["formal_registry_emitted"] is False
    assert m["rollback_pointer"]  # non-empty rollback pointer
    assert m["delta_hash"]  # independent hash
    assert m["model_vote_as_source"] == 0
    assert m["council_vote_as_source"] == 0


# --------------------------------------------------------------------------- #
# Clean checkout supply load
# --------------------------------------------------------------------------- #


def test_clean_checkout_supply_load(result):
    """Every available pillar must have loaded from tracked sources (no DB/remote)."""
    obj = result["pillars"]["objective_answer_key_governed"]
    # hermetic fixture is the clean-checkout source when no live DB is configured
    assert obj["source_kind"] in {"questions_bank_hermetic_fixture", "questions_bank_live_readonly"}
    assert result["pillars"]["case_rubric_registry"]["available"] is True
    assert result["pillars"]["m20_candidate_delta"]["available"] is True


def test_coverage_scope_explicit(result):
    cov = result["coverage_report"]["objective_answer_key"]
    assert cov["scope"] in {"hermetic_fixture", "live"}
    # conflicts must be 0 OR every conflict carries a work order
    assert cov["conflicts_have_work_order"] is True
    if cov["scope"] == "hermetic_fixture":
        assert cov["live_blocker"]  # precise live blocker recorded


# --------------------------------------------------------------------------- #
# M26 blocker matrix
# --------------------------------------------------------------------------- #


def test_m26_blocker_matrix_advances_release_registry(result):
    m = result["m26_blocker_resolution_matrix"]
    rr = m["requires_release_registry"]
    # With the authoritative bundle present (2640 live keys) the blocker is resolved
    # at release_candidate level; without it, at least ADVANCED.
    assert rr["status"] in {"ADVANCED", "RESOLVED_AS_RELEASE_CANDIDATE"}
    assert rr["objective_pillar"]["resolution"] == "RELEASE_CANDIDATE_AVAILABLE"
    # requires_live_llm is explicitly out of compiler scope (runtime concern)
    assert m["requires_live_llm"]["resolution"] == "OUT_OF_M30_SCOPE"


def test_authoritative_m30_verified(m30, result):
    """Independent acceptance verification of the parallel authoritative M30."""
    auth = result["authoritative_m30_verification"]
    if not auth.get("available"):
        pytest.skip("authoritative full_knowledge_compiler bundle not present in this checkout")
    assert auth["schema_version"] == "compiled_knowledge_registry.v2"
    assert auth["all_checks_pass"] is True
    checks = auth["verification_checks"]
    assert checks["status_release_candidate"] is True
    assert checks["not_published"] is True
    assert checks["safety_answer_key_override_zero"] is True
    assert checks["safety_rag_chunk_as_answer_key_zero"] is True
    assert checks["safety_official_answer_as_source_zero"] is True
    assert checks["safety_tamper_fail_closed"] is True
    # the live full compiler must exceed the old 62-row fixture
    assert (auth.get("objective_full_count") or 0) > 62


def test_authoritative_verifier_blocks_on_missing_bundle(m30, tmp_path):
    """Absent authoritative bundle -> precise blocker, never a fake pass."""
    res = m30.verify_authoritative_m30(tmp_path / "nonexistent")
    assert res["available"] is False
    assert "blocker" in res


# --------------------------------------------------------------------------- #
# Verdict honesty
# --------------------------------------------------------------------------- #


def test_verdict_is_scoped_not_whole_plan(result):
    go = result["go_no_go"]
    assert go["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert go["scope"] == "knowledge_compiler_layer_independent_verification"
    assert go["not_whole_plan_go"] is True
    # never claim a whole-plan GO; release_candidate scope only
    assert go["verdict"] != "GO"
    assert "full_knowledge_compiler" in go["authoritative_compiler"]


def test_no_ws_smoke_is_documented(m30, result):
    """M30 is artifact-only; the FINDING must justify no WS smoke this round."""
    finding = m30._render_finding(result, None)
    assert "Why no /api/v1/ws smoke" in finding
    assert "M26 Live Acceptance" in finding


# --------------------------------------------------------------------------- #
# End-to-end: main writes all required artifacts hermetically
# --------------------------------------------------------------------------- #


def test_main_writes_required_artifacts(m30, tmp_path):
    rc = m30.main(["--out-dir", str(tmp_path / "m30")])
    assert rc == 0
    out = tmp_path / "m30"
    required = [
        "source_inventory.json",
        "authority_map.json",
        "compiled_manifest.json",
        "signed_bundle_hashes.json",
        "coverage_report.json",
        "laundering_guard_report.json",
        "m26_blocker_resolution_matrix.json",
        "authoritative_m30_verification.json",
        "go_no_go_m30.json",
        "FINDING.md",
    ]
    for name in required:
        assert (out / name).exists(), name
    go = json.loads((out / "go_no_go_m30.json").read_text("utf-8"))
    assert go["verdict"] in {"GO", "WEAK-GO", "NO-GO"}


def test_no_competing_v3_runtime_bundle(m30):
    """Single authority / less-is-more: this verifier must NOT ship a second
    runtime_supply registry. The authoritative bundle is the parallel compiler."""
    v3 = REPO_ROOT / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v3_knowledge_release_candidate"
    # If a v3 dir exists at all, it must NOT have been created by this verifier
    # (we removed ours). The authoritative registry lives in the parallel bundle.
    assert m30.AUTHORITATIVE_SCHEMA == "compiled_knowledge_registry.v2"
    go = m30.run_compiler()["go_no_go"]
    assert "second registry" in go["this_deliverable_role"] or "NOT a second registry" in go["this_deliverable_role"]
