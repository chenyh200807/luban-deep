"""M7 source-repair factory invariants. Regenerates into tmp from M5 blocked points + 2026 textbook.
Skips if upstream artifacts / textbook absent."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_registry_v1_source_repair_m7 import build_m7, M5_DIR, BOOK_DIR

pytestmark = pytest.mark.skipif(
    not (M5_DIR / "authority_adjudication.json").exists() or not BOOK_DIR.exists(),
    reason="M5 authority or 2026 textbook absent")


@pytest.fixture(scope="module")
def m7(tmp_path_factory):
    out = tmp_path_factory.mktemp("m7")
    return build_m7(out), out


def _jsonl(p):
    return [json.loads(x) for x in Path(p).read_text("utf-8").splitlines() if x.strip()]


def test_all_blocked_points_classified_none_unclassified(m7):
    r, out = m7
    inv = json.loads((out / "blocked_point_inventory.json").read_text("utf-8"))
    assert inv["count"] == r["sim"]["blocked_points_input"]
    assert all(p.get("category") for p in inv["points"])  # no unclassified
    total = r["sim"]["verified_repaired_points"] + r["sim"]["keep_draft_points"] + r["sim"]["drop_or_external_source_points"]
    assert total == inv["count"]  # loop-until-done: every point has a final action


def test_no_official_answer_upgraded_to_textbook(m7):
    r, out = m7
    assert r["sim"]["official_answer_upgraded_to_textbook"] == 0
    for v in _jsonl(out / "verified_repaired_points.jsonl"):
        assert v["verified_source_ref"]["source_type"] == "textbook"
        assert v["verified_source_ref"]["match_method"] == "verbatim"
        assert v["verified_source_ref"]["verified"] is True


def test_final_authority_is_ai_expert_council(m7):
    r, out = m7
    for name in ("verified_repaired_points.jsonl", "keep_draft_points.jsonl", "drop_or_external_source_points.jsonl"):
        for row in _jsonl(out / name):
            assert row["final_authority"] == "ai_expert_council_final"


def test_drop_points_require_external_source(m7):
    r, out = m7
    for row in _jsonl(out / "drop_or_external_source_points.jsonl"):
        assert row["disposition"] == "drop_or_external_source"
        assert row["require_external_source"] is True
        assert row["runtime_auto_certifiable"] is False


def test_semantic_and_figure_never_runtime_auto(m7):
    r, out = m7
    for v in _jsonl(out / "verified_repaired_points.jsonl"):
        assert v["policy_type"] not in ("semantic_allowed", "figure_label")


def test_no_formal_registry_or_runtime_connection(m7):
    r, out = m7
    assert r["sim"]["formal_registry_emitted"] is False
    assert r["sim"]["production_runtime_connected"] is False
    assert not (out / "registry_v1.json").exists()
    assert not (out / "question_grading_registry_v1.json").exists()
    preview = json.loads((out / "runtime_auto_certification_preview.json").read_text("utf-8"))
    assert preview["production_runtime_connected"] is False


def test_council_did_not_fabricate_source_when_no_verbatim_anchor(m7):
    r, out = m7
    # any point with zero candidate anchors must NOT be verified_repaired
    cands = {(c["question_id"], c["point_id"]): c["candidate_count"] for c in _jsonl(out / "per_point_repair_candidates.jsonl")}
    for v in _jsonl(out / "verified_repaired_points.jsonl"):
        assert cands[(v["question_id"], v["point_id"])] > 0  # verified only if a real verbatim candidate existed
    # council spawned no subagents when eligible set was empty (no anchors)
    if r["sim"]["points_with_structured_anchor_terms"] == 0:
        assert r["sim"]["verified_repaired_points"] == 0


def test_theoretical_auto_never_decreases_below_baseline(m7):
    r, _ = m7
    assert r["sim"]["theoretical_auto_certifiable_after_repair"] >= r["sim"]["baseline_auto_certifiable"]
