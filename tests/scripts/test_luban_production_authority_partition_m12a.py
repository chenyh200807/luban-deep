"""Hermetic guards for M12A Production Authority Partition.

Every candidate / residual scoring point must get exactly ONE primary authority_kind
out of the 9-kind taxonomy. No source laundering, no formal registry, no production
runtime — this is a partition + evidence compiler, not a production release.
"""
from __future__ import annotations

import json
from collections import Counter
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
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m12a")
    result = m12a.run_m12a(out_dir=out)
    return out, result


def test_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "authority_taxonomy_m12a.json", "point_authority_partition_m12a.jsonl",
        "evidence_compiler_manifest_m12a.json", "question_stem_fact_evidence_m12a.jsonl",
        "machine_spec_evidence_m12a.jsonl", "list_rule_full_coverage_evidence_m12a.jsonl",
        "external_source_work_orders_m12a.jsonl", "review_only_packets_m12a.jsonl",
        "production_readiness_delta_m12a.json",
        "FINDING_production_authority_partition_m12a_20260604.md",
    ):
        assert (out / name).exists(), name


def test_taxonomy_has_nine_authority_kinds(run):
    out, _ = run
    tax = _j(out / "authority_taxonomy_m12a.json")
    assert set(tax["authority_kinds"]) == set(m12a.ALL_KINDS)
    assert len(m12a.ALL_KINDS) == 9


def test_every_point_has_exactly_one_authority_kind(run):
    out, _ = run
    partition = _jsonl(out / "point_authority_partition_m12a.jsonl")
    assert partition
    for rec in partition:
        assert rec["authority_kind"] in m12a.ALL_KINDS
    # one row per (question_id, point_id)
    keys = [(r["question_id"], r["point_id"]) for r in partition]
    assert len(keys) == len(set(keys))


def test_classification_is_complete(run):
    out, result = run
    delta = _j(out / "production_readiness_delta_m12a.json")
    assert delta["classification_coverage"] == 1.0
    assert sum(delta["kind_counts"].values()) == delta["total_points"]
    assert result["total_points"] == delta["total_points"]


def test_production_readiness_delta_is_explicit(run):
    out, _ = run
    delta = _j(out / "production_readiness_delta_m12a.json")
    assert delta["textbook_authorized"] == 23
    assert delta["spec_authorized"] == 45          # 24 calc + 21 logic
    assert delta["list_authorized"] == 14
    assert delta["theoretical_auto_shadow_supply"] == 82   # 23 textbook + 45 machine + 14 list
    assert delta["auto_shadow_breakdown"] == {"textbook_auto": 23, "machine_spec_auto": 45, "list_auto": 14}
    assert delta["production_formal_registry"] == "NO-GO"
    assert delta["production_runtime_connected"] is False


def test_verdict_is_partition_go_not_production_go(run):
    out, result = run
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert result["verdict"] == "GO"
    assert result["source_laundering"] == 0
    assert result["production_formal_registry"] == "NO-GO"
    finding = (out / "FINDING_production_authority_partition_m12a_20260604.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "仍 NO-GO" in finding


def test_spec_attack_invariant_recorded(run):
    out, _ = run
    manifest = _j(out / "evidence_compiler_manifest_m12a.json")
    assert manifest["spec_false_positive_total"] == 0
    assert manifest["all_specs_pass_attack"] is True
    assert manifest["specs_attacked"] == 59  # 45 machine + 14 list
