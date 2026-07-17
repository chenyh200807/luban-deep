from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "build_luban_mother_topic_coverage_matrix.py"
SPEC = importlib.util.spec_from_file_location("mother_topic_coverage", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_matrix_closes_the_60_slot_registry() -> None:
    audit = mod.build_matrix()
    assert audit["counts"]["capability_slots"] == 60
    assert audit["counts"]["existing_mother_topics"] == 41
    assert audit["counts"]["missing_slots"] == 19
    assert len(audit["rows"]) == 60


def test_missing_slots_are_not_treated_as_automatic_new_topics() -> None:
    rows = {row["capability_id"]: row for row in mod.build_matrix()["rows"]}
    assert rows["E04"]["worth_adding"] == "yes_candidate"
    assert rows["E04"]["recommended_action"] == "add_after_exam_evidence"
    assert {"E03", "K04"}.issubset(rows["E04"]["overlap_registry_capabilities"])
    assert rows["E02"]["recommended_action"] == "enrich_existing_instead"
    assert rows["G05"]["recommended_action"] == "enrich_existing_instead"
    assert rows["K02"]["recommended_action"] == "merge_into_planned_parent"
    assert rows["D15"]["recommended_action"] == "split_only_with_evidence"


def test_existing_topics_keep_data_asset_not_product_semantics() -> None:
    rows = {row["capability_id"]: row for row in mod.build_matrix()["rows"]}
    assert rows["N01"]["coverage_strength"] == "strong_direct"
    assert rows["N01"]["exam_evidence_hits_candidate"] == 27
    assert rows["E05"]["coverage_strength"] == "source_grounded_exam_zero"
    assert rows["E05"]["worth_adding"] == "no"
