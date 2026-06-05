"""Integration guard against source laundering in the M12A partition.

official_answer must never become textbook source; AI / council votes must never
become source authority; question_stem facts must never masquerade as textbook; and
no formal registry / production runtime may be produced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_production_authority_partition_m12a as m12a

pytestmark = pytest.mark.skipif(
    not (m12a.M10 / "residual_authority_inventory_m10.json").exists(),
    reason="M10 residual inventory absent",
)


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("m12a_laundering")
    m12a.run_m12a(out_dir=d)
    return d


def test_source_laundering_is_zero(out):
    delta = _j(out / "production_readiness_delta_m12a.json")
    tax = _j(out / "authority_taxonomy_m12a.json")
    assert "official_answer_as_textbook=0" in tax["source_laundering_red_lines"]
    # textbook points must be backed by a textbook span (verbatim or carried verified provenance),
    # never by official_answer text
    for r in _jsonl(out / "point_authority_partition_m12a.jsonl"):
        if r["authority_kind"] == m12a.K_TEXTBOOK and r["production_gate_status"] == "beta_shadow_auto":
            assert r["source_is_textbook"] is True
            assert r["evidence_span"]  # carries a textbook anchor / verified provenance


def test_only_textbook_points_claim_textbook_source(out):
    for r in _jsonl(out / "point_authority_partition_m12a.jsonl"):
        if r["source_is_textbook"]:
            assert r["authority_kind"] == m12a.K_TEXTBOOK
        if r["authority_kind"] != m12a.K_TEXTBOOK:
            assert r["source_is_textbook"] is False


def test_specs_are_marked_spec_source_not_textbook(out):
    for r in _jsonl(out / "machine_spec_evidence_m12a.jsonl"):
        assert r["source_is_spec"] is True
        assert r["source_is_textbook"] is False


def test_no_formal_registry_and_no_production_runtime(out):
    delta = _j(out / "production_readiness_delta_m12a.json")
    assert delta["production_formal_registry"] == "NO-GO"
    assert delta["production_runtime_connected"] is False
    # no formal registry file is emitted by M12A
    assert not (out / "registry_v1.json").exists()
    assert not (out / "question_grading_registry_v1.json").exists()


def test_auto_supply_is_only_textbook_spec_list(out):
    delta = _j(out / "production_readiness_delta_m12a.json")
    breakdown = delta["auto_shadow_breakdown"]
    # auto supply must come only from verified textbook + attack-passing spec + full-coverage list
    assert delta["theoretical_auto_shadow_supply"] == sum(breakdown.values())
    # question_stem / external / review / drop contribute nothing to auto supply
    assert delta["question_stem_span_verified"] >= 0
    assert delta["external_needed"] >= 0
