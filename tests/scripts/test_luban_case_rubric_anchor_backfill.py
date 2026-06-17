"""Tests for M2 textbook-anchor backfill artifacts.

The backfill may upgrade draft packet copies when a point has a strict
content_markdown verbatim anchor. It must not mutate the original M2 packet,
promote official answers, or emit a formal registry.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_case_rubric_anchor_backfill import build_anchor_backfill_artifacts
from scripts.luban_case_rubric_schema import TEXTBOOK, validate_audit_packet, verify_textbook_anchor


M2_DIR = Path("artifacts/luban_grading_artifacts/case_rubric_expansion_m2_20260604")


def _read(path: Path):
    return json.loads(path.read_text("utf-8"))


def _build(tmp_path: Path) -> Path:
    build_anchor_backfill_artifacts(out_dir=tmp_path)
    return tmp_path


def test_backfill_worklist_uses_only_m2_weak_points(tmp_path: Path):
    out = _build(tmp_path)
    worklist = _read(out / "weak_anchor_worklist.json")

    assert len(worklist) == 12
    assert all(item["question_id"].startswith("M2-") for item in worklist)
    assert all(item["current_anchor_status"] == "weak" for item in worklist)
    assert all(item["search_terms"] for item in worklist)


def test_verified_source_requires_chunk_quote_and_normalized_match(tmp_path: Path):
    out = _build(tmp_path)
    results = _read(out / "textbook_anchor_search_results.json")

    for row in results:
        if row["decision"] != "verified":
            continue
        hit = row["selected_hit"]
        assert hit
        anchor = {
            "source_type": TEXTBOOK,
            "chunk_id": hit["chunk_id"],
            "textbook_quote": hit["quote"],
            "verified": True,
            "match_method": "verbatim",
        }
        assert verify_textbook_anchor(anchor)
        assert hit["normalized_match"] is True
        assert hit["match_type"] == "verbatim_normalized"
        assert hit["term_seed_source"] in {"label", "required_terms", "calculation_spec", "official_answer_span"}
        assert not hit["matched_term"].lower().endswith(("mm", "cm", "m2", "m3"))


def test_official_answer_and_node_seed_are_never_auto_source(tmp_path: Path):
    out = _build(tmp_path)

    for packet_path in sorted((out / "audit_packets_backfilled").glob("*.json")):
        packet = _read(packet_path)
        for point in packet["scoring_points"]:
            if not point.get("auto_certifiable"):
                continue
            refs = point.get("source_refs") or []
            assert refs
            assert refs[0]["source_type"] == TEXTBOOK
            assert refs[0]["source_type"] != "official_answer"
            assert refs[0]["source_type"] != "node_asset_seed"


def test_still_weak_points_are_not_auto_certifiable(tmp_path: Path):
    out = _build(tmp_path)
    results = {
        (row["question_id"], row["point_id"]): row
        for row in _read(out / "textbook_anchor_search_results.json")
    }

    for packet_path in sorted((out / "audit_packets_backfilled").glob("*.json")):
        packet = _read(packet_path)
        assert validate_audit_packet(packet) == []
        for point in packet["scoring_points"]:
            result = results[(packet["question_id"], point["point_id"])]
            if result["decision"] != "verified":
                assert point["auto_certifiable"] is False


def test_backfill_does_not_overwrite_original_m2_artifact(tmp_path: Path):
    original_path = M2_DIR / "audit_packets" / "M2-2015-EXAM_XW2015_CASE_1-01.json"
    before = original_path.read_text("utf-8")

    _build(tmp_path)

    assert original_path.read_text("utf-8") == before


def test_registry_impact_is_simulation_only(tmp_path: Path):
    out = _build(tmp_path)
    impact = _read(out / "registry_impact_after_backfill.json")

    assert impact["formal_registry_emitted"] is False
    assert impact["simulation_only"] is True
    assert not (out / "registry_v1.json").exists()
