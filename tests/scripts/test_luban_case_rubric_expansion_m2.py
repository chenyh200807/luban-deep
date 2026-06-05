"""M2 case-rubric expansion artifact tests.

These tests lock the production-safety boundary: M2 may collect candidates and
produce draft audit packets, but it must not publish a registry, promote weak
sources, or represent model review as human review.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_case_rubric_expansion_m2 import build_m2_artifacts
from scripts.luban_case_rubric_schema import validate_audit_packet, verify_textbook_anchor


def _build(tmp_path: Path) -> Path:
    build_m2_artifacts(out_dir=tmp_path)
    return tmp_path


def _read(path: Path):
    return json.loads(path.read_text("utf-8"))


def test_m2_collects_case_candidates_and_excludes_mcq(tmp_path: Path):
    out = _build(tmp_path)
    candidates = _read(out / "candidate_case_questions.json")
    excluded = _read(out / "excluded_mcq.json")

    assert 1 <= len(candidates) <= 30
    assert all(c["is_gradeable_case_candidate"] for c in candidates)
    assert all(c["question_text"] and c["official_answer"] for c in candidates)
    assert excluded
    assert all(e["source_type"] in {"single_choice", "multi_choice", "multiple_choice", "true_false"} for e in excluded)


def test_m2_audit_packets_validate_against_a1_schema(tmp_path: Path):
    out = _build(tmp_path)
    packets = sorted((out / "audit_packets").glob("*.json"))

    assert 3 <= len(packets) <= 5
    for packet_path in packets:
        packet = _read(packet_path)
        assert validate_audit_packet(packet) == []
        assert packet["artifact_status"] == "draft"


def test_m2_weak_sources_are_not_auto_certifiable(tmp_path: Path):
    out = _build(tmp_path)

    for packet_path in sorted((out / "audit_packets").glob("*.json")):
        packet = _read(packet_path)
        for point in packet["scoring_points"]:
            if point.get("source_status") == "missing_or_weak":
                assert point["auto_certifiable"] is False


def test_m2_verified_anchor_shape_is_strict(tmp_path: Path):
    out = _build(tmp_path)
    audit = _read(out / "textbook_anchor_audit.json")

    for row in audit["point_anchor_audit"]:
        if row["anchor_status"] == "verified":
            anchor = {
                "source_type": "textbook",
                "chunk_id": row["chunk_id"],
                "textbook_quote": row["textbook_quote"],
                "match_method": "verbatim",
                "verified": True,
            }
            assert verify_textbook_anchor(anchor)
            assert row["normalized_match"]
        else:
            assert row["anchor_status"] in {"weak", "missing", "blocked"}


def test_m2_llm_jury_metadata_does_not_impersonate_human(tmp_path: Path):
    out = _build(tmp_path)
    jury = _read(out / "llm_jury_rubric_candidates.json")

    assert jury["review_source"] == "model_jury_rubric_review"
    assert jury["reviewer_type"] == "llm_jury"
    assert jury["reviewer_type"] != "manual_qa_teacher"
    assert jury["model_votes"] == []
    assert set(jury["unavailable_models"]) == {"gpt55", "opus48", "deepseek_v4", "qwen37"}


def test_m2_registry_impact_is_simulation_only(tmp_path: Path):
    out = _build(tmp_path)
    impact = _read(out / "registry_impact_simulation.json")

    assert impact["formal_registry_emitted"] is False
    assert impact["new_published_count"] == 0
    assert impact["new_draft_count"] >= 3
    assert not (out / "registry_v1.json").exists()
