"""Living LLM Artifact Compiler — feedback ingest bridge (S0 + S7 producer).

Proves the bridge gives compiler_feedback its first producer, stamps the immutable origin/source
boundary correctly (official_answer = seed, not governed source), content-addresses for loop dedup,
and routes M20 deltas through the existing absorber. Hermetic.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import compiler_feedback as CF
from deeptutor.services.construction_grading import feedback_ingest_bridge as B


def test_evidence_item_content_addressed_and_origin_immutable():
    item = B.make_evidence_item(evidence_kind="machine_spec_point", payload={"point_id": "P1", "text": "工期顺延 25 天"})
    assert item["evidence_kind"] == "machine_spec_point"
    assert item["origin"] == "questions_bank"  # default
    assert item["source_kind"] == "non_governed"  # machine-checkable, not governed textbook
    assert item["is_governed_source"] is False
    assert len(item["evidence_id"]) == 16
    # same content -> same id (dedup); different payload -> different id
    again = B.make_evidence_item(evidence_kind="machine_spec_point", payload={"point_id": "P1", "text": "工期顺延 25 天"})
    assert again["evidence_id"] == item["evidence_id"]
    other = B.make_evidence_item(evidence_kind="machine_spec_point", payload={"point_id": "P2", "text": "x"})
    assert other["evidence_id"] != item["evidence_id"]


def test_official_answer_is_seed_not_governed_source():
    item = B.make_evidence_item(evidence_kind="case_official_answer", payload={"answer": "工期顺延，索赔成立"})
    assert item["source_kind"] == "non_governed"
    assert item["is_governed_source"] is False  # official_answer can NEVER back a textbook source


def test_textbook_block_is_governed():
    item = B.make_evidence_item(evidence_kind="textbook_block", payload={"content_markdown": "..."})
    assert item["source_kind"] == "governed_textbook"
    assert item["is_governed_source"] is True


def test_ingest_sources_dedups():
    rows = [{"point_id": "P1", "text": "同"}, {"point_id": "P1", "text": "同"}, {"point_id": "P2", "text": "异"}]
    items = B.ingest_sources(machine_spec_points=rows, run_id="r1")
    assert len(items) == 2  # duplicate collapsed


def test_unknown_evidence_kind_rejected():
    import pytest

    with pytest.raises(ValueError):
        B.make_evidence_item(evidence_kind="not_a_kind", payload={})


def test_open_world_to_candidates_uses_existing_producer():
    diag = {"candidate_work_order": {"prompt_excerpt": "某变体题", "evidence_ref_count": 2}, "uncertainty_label": "low"}
    cands = B.open_world_to_candidates(diag)
    assert len(cands) == 2
    kinds = {c["kind"] for c in cands}
    assert CF.KIND_QUESTION in kinds and CF.KIND_WORK_ORDER in kinds
    assert all(c["promote_to_release"] is False for c in cands)  # never promotable at birth


def test_m20_delta_absorber_wired():
    deltas = [
        {"delta_id": "d1", "delta_kind": "rubric_delta", "origin": "teacher_review", "source_backed": True},
        {"delta_id": "d2", "delta_kind": "rubric_delta", "origin": "model_vote", "source_backed": False},
    ]
    out = B.absorb_m20_deltas(deltas)
    rc_ids = {e["delta_id"] for e in out["release_candidate"]}
    wo_ids = {e["delta_id"] for e in out["work_order"]}
    assert "d1" in rc_ids                      # governed + source-backed -> release_candidate
    assert "d2" in wo_ids                      # model_vote not source-backed -> work_order (never promoted)
    assert out["candidate_used_as_release_truth"] == 0


def test_reingest_terminal_only_work_orders_and_rejects_and_dedups():
    entries = [
        CF.make_candidate(kind=CF.KIND_WORK_ORDER, origin="open_world_diagnostic", payload={"task": "x"}),
        CF.make_candidate(kind=CF.KIND_RUBRIC, origin="llm_guess", payload={"text": "y"}),  # not terminal
    ]
    seen: set[str] = set()
    out = B.reingest_terminal(entries, seen=seen, run_id="r2")
    assert len(out) == 1                        # only the work_order re-ingested
    assert out[0]["evidence_kind"] == "runtime_miss"
    # second pass with same seen -> nothing new (bounded loop)
    out2 = B.reingest_terminal(entries, seen=seen, run_id="r3")
    assert out2 == []
