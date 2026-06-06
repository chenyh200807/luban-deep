"""M30R: assert the canonical M30 pointer + supersession are well-formed and single-authority.

Read-only over the reconciliation artifacts; no recompile. Guards against a future regression where a
second variant claims canonical or an auditor hash leaks in as the runtime authority."""
from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_R = _REPO / "artifacts" / "luban_grading_artifacts" / "m30_canonical_reconciliation_20260606"
CANONICAL_REG_HASH = "9395cacc060fe480e80f81e5effbf68690b94803ff7f4afb8e0848995a7bebc3"
CANONICAL_OBJ_HASH = "672ff9a653adf2d00b6501b4d6934e836b34b5d37608ad4d3169d672b41c1bdd"


def _load(name):
    return json.loads((_R / name).read_text("utf-8"))


def test_canonical_pointer_is_single_and_pins_full_knowledge_compiler() -> None:
    p = _load("canonical_manifest_pointer.json")
    assert "full_knowledge_compiler_release_candidate_m30_20260606" in p["canonical_manifest"]
    assert p["schema_version"] == "compiled_knowledge_registry.v2"
    assert p["registry_content_hash"] == CANONICAL_REG_HASH
    assert p["objective_lane"]["content_hash"] == CANONICAL_OBJ_HASH
    assert p["objective_lane"]["count"] == 2640
    assert p["status"] == "release_candidate"
    assert p["published"] is False
    assert p["canonical_truth_written"] is False


def test_every_variant_has_a_disposition_and_only_one_canonical() -> None:
    m = _load("m30_supersession_matrix.json")["dispositions"]
    # exactly one ARTIFACT DIR is canonical (the producer script is also CANONICAL but is not a manifest)
    canonical_dirs = [k for k, v in m.items()
                      if str(v).startswith("CANONICAL") and not k.startswith("scripts/")]
    assert len(canonical_dirs) == 1
    assert "full_knowledge_compiler_release_candidate_m30_20260606" in canonical_dirs[0]
    # the other two compiler artifact dirs must be auditor-only
    assert "AUDITOR-ONLY" in m["knowledge_compiler_release_candidate_m30_20260606 (B)"]
    assert "AUDITOR-ONLY" in m["full_knowledge_compiler_release_candidate_m30_20260606_auditor_readonly (C)"]


def test_auditor_hashes_are_not_the_canonical_authority() -> None:
    c = _load("schema_and_hash_consistency_report.json")
    assert c["canonical"]["registry_content_hash"] == CANONICAL_REG_HASH
    # B's own re-sign and C's re-run hashes must be flagged auditor-only, never canonical
    assert "auditor-only" in c["cross_variant_hashes"]["B_own_resign"]
    assert "auditor-only" in c["cross_variant_hashes"]["C_readonly_rerun"]


def test_safety_recheck_all_clean_and_no_publish() -> None:
    s = _load("safety_invariant_recheck.json")
    assert s["all_clean"] is True
    h = s["hard_acceptance"]
    for z in ("source_laundering", "rag_chunk_as_answer_key", "model_vote_as_source",
              "official_answer_as_source", "client_supplied_answer_key_release_truth",
              "candidate_used_as_release_truth", "production_write_count"):
        assert h[z] == 0
    assert h["tamper_fail_closed"] is True
    assert h["published_registry"] is False
    assert h["canonical_truth_written"] is False


def test_verdict_is_weak_go_with_persistence_blocker() -> None:
    g = _load("go_no_go_m30r.json")
    assert g["verdict"] == "WEAK-GO"
    assert any("PERSISTENCE" in b for b in g["blockers"])
    assert g["variant_dispositions"]["A_full_knowledge_compiler"] == "CANONICAL"
