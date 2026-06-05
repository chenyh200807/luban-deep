"""M13C external standard source rescue guards.

M13C is supply-line only. It may verify external standard source spans or create
operator work orders, but it must not use official answers/model votes/council
votes as source authority and must not emit a formal registry.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_external_standard_source_rescue_m13c as m13c

pytestmark = pytest.mark.skipif(
    not (m13c.M12A / "external_source_work_orders_m12a.jsonl").exists(),
    reason="M12A external work orders absent",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def m13c_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m13c")
    result = m13c.run_m13c(out_dir=out)
    return out, result


def test_external_inventory_covers_all_13_m12a_points(m13c_run):
    out, result = m13c_run
    inventory = _json(out / "external_source_inventory_m13c.json")
    assert inventory["input_external_point_count"] == 13
    assert inventory["covered_point_count"] == 13
    assert result["covered_point_count"] == 13
    decisions = inventory["decision_counts"]
    assert sum(decisions.values()) == 13
    assert set(decisions) <= {"external_verified", "external_pending", "review_only", "drop"}


def test_verified_sources_are_external_standard_verbatim_matches(m13c_run):
    out, _ = m13c_run
    verified = _jsonl(out / "external_verified_sources_m13c.jsonl")
    standard_index = m13c.load_standard_source_index()
    by_key = {
        (row["source_file"], row["node_id"], row["verbatim_span_hash"]): row
        for row in standard_index
    }
    for row in verified:
        assert row["authority_kind"] == "external_standard_source"
        assert row["source_is_textbook"] is False
        assert row["source_type"] == "standard_origin_text"
        assert row["verbatim_span"]
        assert row["match_hash"]
        source = by_key[(row["source_file"], row["node_id"], row["verbatim_span_hash"])]
        assert m13c.normalized_contains(source["origin_text"], row["verbatim_span"])


def test_pending_work_orders_are_not_fake_sources(m13c_run):
    out, _ = m13c_run
    pending = _jsonl(out / "external_pending_work_orders_m13c.jsonl")
    inventory = _json(out / "external_source_inventory_m13c.json")
    assert len(pending) == inventory["decision_counts"].get("external_pending", 0)
    for row in pending:
        assert row["decision"] == "external_pending"
        assert row["authority_kind"] == "external_standard_source"
        assert row["verified"] is False
        assert row["source_file"] is None
        assert row["needed_source"]
        assert row["why_textbook_cannot_prove"]
        assert row["operator_search_keywords"]


def test_laundering_audit_blocks_non_authoritative_sources(m13c_run):
    out, _ = m13c_run
    audit = _json(out / "external_source_laundering_audit_m13c.json")
    assert audit["input_external_point_count"] == 13
    assert audit["official_answer_as_external_source"] == 0
    assert audit["model_vote_as_source"] == 0
    assert audit["council_vote_as_source"] == 0
    assert audit["external_as_textbook"] == 0
    assert audit["verified_without_verbatim_exact_match"] == 0
    assert audit["production_runtime_connected"] is False
    assert audit["formal_registry_emitted"] is False


def test_finding_answers_supply_impact_and_no_registry(m13c_run):
    out, result = m13c_run
    finding = (out / "FINDING_external_standard_source_rescue_m13c_20260604.md").read_text("utf-8")
    assert "formal_registry_emitted=false" in finding
    assert "production_runtime_connected=false" in finding
    assert "official_answer_as_external_source=0" in finding
    assert result["verified_count"] + result["pending_count"] + result["review_only_count"] + result["drop_count"] == 13
    assert not (out / "registry_v1.json").exists()
