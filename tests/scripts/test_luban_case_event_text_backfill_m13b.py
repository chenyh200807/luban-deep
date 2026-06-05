"""Guards for M13B case-event-text backfill (question-stem authority supply line).

A question_stem_fact must never be laundered into a textbook source, and the
official_answer must never be used as the stem source. Verified points must have a real
exact span; missing full text must become a work order, never fabricated text.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_case_event_text_backfill_m13b as m13b

pytestmark = pytest.mark.skipif(
    not (m13b.M12A_DIR / "question_stem_fact_evidence_m13b.jsonl").exists()
    and not (m13b.M12A_DIR / "question_stem_fact_evidence_m12a.jsonl").exists(),
    reason="M12A stem-fact supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_m13b():
    subprocess.run([sys.executable, str(m13b.REPO / "scripts/run_luban_case_event_text_backfill_m13b.py")],
                   cwd=m13b.REPO, check=True, capture_output=True)
    return m13b.OUT_DIR


def test_all_nine_stem_facts_are_covered():
    rows = _jsonl(m13b.OUT_DIR / "question_stem_span_verification_m13b.jsonl")
    assert len(rows) == 9
    for r in rows:
        assert r["classification"] in ("verified", "pending", "impossible")  # never unknown


def test_verified_points_have_exact_span_against_stem_only():
    rows = _jsonl(m13b.OUT_DIR / "question_stem_span_verification_m13b.jsonl")
    for r in rows:
        if r["classification"] == "verified":
            assert r["span_exact_match"] is True
            assert r["matched_against"] == "question_stem_text_only"
            assert r["official_answer_used_as_source"] is False


def test_question_stem_fact_is_never_textbook_authority():
    audit = _j(m13b.OUT_DIR / "case_event_text_source_audit_m13b.json")
    assert audit["question_stem_as_textbook"] == 0
    rows = _jsonl(m13b.OUT_DIR / "question_stem_span_verification_m13b.jsonl")
    for r in rows:
        assert r["is_textbook_source"] is False


def test_official_answer_is_never_the_stem_source():
    audit = _j(m13b.OUT_DIR / "case_event_text_source_audit_m13b.json")
    assert audit["official_answer_as_question_stem_source"] == 0


def test_production_auto_zero_and_runtime_unchanged():
    audit = _j(m13b.OUT_DIR / "case_event_text_source_audit_m13b.json")
    assert audit["production_auto_count"] == 0
    assert audit["runtime_changed"] is False
    assert audit["beta_loader_changed"] is False
    assert audit["registry_emitted"] is False
    assert audit["fabricated_text"] is False


def test_pending_and_impossible_points_get_work_orders_not_fabrication():
    rows = _jsonl(m13b.OUT_DIR / "question_stem_span_verification_m13b.jsonl")
    work_orders = _jsonl(m13b.OUT_DIR / "pending_case_text_work_orders_m13b.jsonl")
    need_wo = {(r["question_id"], r["point_id"]) for r in rows
               if r["classification"] in ("pending", "impossible")}
    have_wo = {(w["question_id"], w["point_id"]) for w in work_orders}
    assert need_wo == have_wo
    for w in work_orders:
        assert "fabricate stem text" in w["must_not"]
        assert "use official_answer as the stem source" in w["must_not"]


def test_inventory_reports_full_text_availability_honestly():
    inv = _j(m13b.OUT_DIR / "case_event_text_inventory_m13b.json")
    assert inv["official_answer_excluded_from_stem_sources"] is True
    # consumability claim must match verified count
    audit = _j(m13b.OUT_DIR / "case_event_text_source_audit_m13b.json")
    assert audit["consumable_by_m13_m14"] == (audit["verified_count"] > 0)
