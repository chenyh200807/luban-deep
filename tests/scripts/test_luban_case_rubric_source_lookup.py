"""Tests for M2 still-weak source lookup artifacts.

Source lookup may find textbook/standard/official candidates for still-weak
points, but only textbook content_markdown matches can become auto-certifiable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_case_rubric_source_lookup import (
    _auto_certifiable_for_decision,
    _normalize,
    build_source_lookup_artifacts,
)


BACKFILL_DIR = Path("artifacts/luban_grading_artifacts/case_rubric_anchor_backfill_20260604")


def _read(path: Path):
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def built_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("source_lookup")
    build_source_lookup_artifacts(out_dir=out)
    return out


def test_source_lookup_starts_from_ten_still_weak_points(built_out: Path):
    out = built_out
    worklist = _read(out / "still_weak_source_worklist.json")

    assert len(worklist) == 10
    assert all(item["candidate_source_types"] == ["textbook", "standard", "official_answer"] for item in worklist)
    assert all(item["search_terms"] for item in worklist)


def test_official_weak_is_not_auto_certifiable(built_out: Path):
    out = built_out
    rows = _read(out / "source_lookup_results.json")
    official_rows = [row for row in rows if row["decision"] == "official_weak"]

    assert official_rows
    assert all(row["auto_certifiable"] is False for row in official_rows)
    for row in official_rows:
        assert row["selected_source"]["source_type"] in {"official_answer", "exam_explanation"}


def test_source_gap_is_not_auto_certifiable_policy():
    assert _auto_certifiable_for_decision("source_gap") is False


def test_verified_textbook_requires_quote_match_if_present(built_out: Path):
    out = built_out
    rows = _read(out / "source_lookup_results.json")

    for row in rows:
        if row["decision"] != "verified_textbook":
            continue
        source = row["selected_source"]
        assert source["chunk_id"]
        assert source["quote"]
        assert source["verified"] is True
        assert source["match_type"] == "verbatim_normalized"
        assert source["term_seed_source"] in {"label_or_official_span", "required_terms", "calculation_spec"}
        content = Path(source["source_file"]).read_text("utf-8")
        assert _normalize(source["quote"]) in _normalize(content)


def test_verified_standard_is_candidate_not_direct_publish(built_out: Path):
    out = built_out
    rows = _read(out / "source_lookup_results.json")

    for row in rows:
        if row["decision"] != "verified_standard":
            continue
        assert row["auto_certifiable"] is False
        assert row["standard_verified_candidate"] is True
        assert row["selected_source"]["source_type"] == "standard"


def test_source_lookup_does_not_overwrite_anchor_backfill(tmp_path: Path):
    original_path = BACKFILL_DIR / "audit_packets_backfilled" / "M2-2016-EXAM_XW2016_CASE_1-01.json"
    before = original_path.read_text("utf-8")

    build_source_lookup_artifacts(out_dir=tmp_path)

    assert original_path.read_text("utf-8") == before


def test_source_lookup_registry_impact_is_simulation_only(built_out: Path):
    out = built_out
    impact = _read(out / "registry_impact_after_source_lookup.json")

    assert impact["simulation_only"] is True
    assert impact["formal_registry_emitted"] is False
    assert impact["input_still_weak_count"] == 10
    assert not (out / "registry_v1.json").exists()
