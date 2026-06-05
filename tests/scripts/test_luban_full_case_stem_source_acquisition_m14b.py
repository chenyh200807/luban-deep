"""M14B full case-stem source acquisition guards.

M14B is a content-supply job. It may import auditable full case stems from local
question-bank / OCR / public web sources, but it must never launder official
answers, answer explanations, AI text, or question-stem facts into textbook
authority or production registry output.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_full_case_stem_source_acquisition_m14b as m14b

pytestmark = pytest.mark.skipif(
    not (m14b.M13B / "pending_case_text_work_orders_m13b.jsonl").exists(),
    reason="M13B pending case-stem work orders absent",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def m14b_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m14b")
    result = m14b.run_m14b(out_dir=out)
    return out, result


def test_nine_pending_work_orders_are_fully_covered(m14b_run):
    out, result = m14b_run
    manifest = _json(out / "source_acquisition_manifest_m14b.json")
    inventory = _jsonl(out / "pending_work_order_inventory_m14b.jsonl")
    assert manifest["input_work_order_count"] == 9
    assert manifest["covered_work_order_count"] == 9
    assert result["covered_work_order_count"] == 9
    assert len(inventory) == 9
    assert {row["final_disposition"] for row in inventory} <= {
        "local_source_found",
        "pdf_ocr_needed",
        "web_public_source_found",
        "source_unavailable",
        "not_recoverable_without_user_material",
    }


def test_verified_stems_are_auditable_non_answer_sources(m14b_run):
    out, _ = m14b_run
    verified = _jsonl(out / "verified_full_case_stems_m14b.jsonl")
    for row in verified:
        assert row["source_kind"] in {"local_question_bank", "pdf_ocr", "web_public"}
        assert row["source_field"] in {"stem", "content_markdown", "pdf_ocr_text", "web_page_text"}
        assert row["full_case_stem"]
        assert row["source_file"] or row["source_url"]
        assert row["official_answer_as_stem_source"] is False
        assert row["answer_explanation_as_stem_source"] is False
        assert row["ai_generated_text_as_stem_source"] is False
        assert row["question_stem_as_textbook"] is False


def test_verified_exact_match_rows_match_required_spans(m14b_run):
    out, _ = m14b_run
    exact_rows = _jsonl(out / "question_stem_exact_match_after_import_m14b.jsonl")
    verified_stems = {
        row["stem_id"]: row for row in _jsonl(out / "verified_full_case_stems_m14b.jsonl")
    }
    for row in exact_rows:
        if row["span_exact_match"]:
            assert row["matched_required_span"]
            assert row["stem_id"] in verified_stems
            assert m14b.normalized_contains(
                verified_stems[row["stem_id"]]["full_case_stem"],
                row["matched_required_span"],
            )
            assert row["official_answer_used_as_source"] is False
            assert row["matched_against"] == "full_case_stem_only"


def test_laundering_counters_are_zero_and_runtime_is_untouched(m14b_run):
    out, _ = m14b_run
    audit = _json(out / "source_laundering_audit_m14b.json")
    assert audit["official_answer_as_stem_source"] == 0
    assert audit["ai_generated_text_as_stem_source"] == 0
    assert audit["answer_explanation_as_stem_source"] == 0
    assert audit["question_stem_as_textbook"] == 0
    assert audit["production_auto_count"] == 0
    assert audit["runtime_changed"] is False
    assert audit["formal_registry_emitted"] is False


def test_ocr_or_web_provenance_is_recorded(m14b_run):
    out, _ = m14b_run
    provenance = _jsonl(out / "ocr_or_web_source_provenance_m14b.jsonl")
    assert provenance
    assert all(row.get("provenance_kind") for row in provenance)
    assert any(row["provenance_kind"] in {"pdf_ocr_surface_checked", "web_public_search_checked"}
               for row in provenance)


def test_rejected_candidates_do_not_become_import_pack_sources(m14b_run):
    out, _ = m14b_run
    rejected = _jsonl(out / "rejected_stem_candidates_m14b.jsonl")
    import_pack = _json(out / "m14_m15_consumable_import_pack_m14b.json")
    import_stem_ids = set(import_pack["verified_stem_ids"])
    assert rejected
    assert all(row["candidate_id"] not in import_stem_ids for row in rejected)
    assert any(row["rejection_reason"] == "answer_or_explanation_not_question_stem_source"
               for row in rejected)


def test_import_pack_reports_go_level_without_formal_registry(m14b_run):
    out, result = m14b_run
    import_pack = _json(out / "m14_m15_consumable_import_pack_m14b.json")
    assert import_pack["go_no_go"] in {"GO", "WEAK-GO", "NO-GO"}
    assert import_pack["formal_registry_emitted"] is False
    assert import_pack["runtime_changed"] is False
    assert import_pack["production_v1_status"] == "NO-GO"
    assert result["go_no_go"] == import_pack["go_no_go"]
    assert not (out / "registry_v1.json").exists()
