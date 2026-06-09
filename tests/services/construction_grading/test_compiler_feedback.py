from __future__ import annotations

from deeptutor.services.construction_grading import compiler_feedback as cf


def test_governed_origin_can_seed_answer_key_candidate() -> None:
    entry = cf.make_candidate(
        kind=cf.KIND_ANSWER_KEY,
        origin="questions_bank",
        payload={"question_id": "Q1", "answer_key": "B"},
    )
    assert entry["kind"] == cf.KIND_ANSWER_KEY
    assert entry["promote_to_release"] is False
    assert entry["namespace"] == cf.NAMESPACE


def test_rag_chunk_cannot_become_answer_key_source_laundering_blocked() -> None:
    entry = cf.make_candidate(
        kind=cf.KIND_ANSWER_KEY,
        origin="rag_chunk",
        payload={"question_id": "Q1", "answer_key": "C"},
    )
    assert entry["kind"] == cf.KIND_REJECTED
    assert entry["reason"].startswith("source_laundering_blocked")


def test_model_and_council_vote_cannot_become_answer_key() -> None:
    for origin in ("model_vote", "council_vote", "llm_guess"):
        entry = cf.make_candidate(kind=cf.KIND_ANSWER_KEY, origin=origin, payload={"answer_key": "A"})
        assert entry["kind"] == cf.KIND_REJECTED


def test_rag_chunk_may_seed_source_candidate() -> None:
    entry = cf.make_candidate(
        kind=cf.KIND_SOURCE,
        origin="rag_chunk",
        payload={"chunk_id": "kb1", "content_hash": "h1"},
    )
    assert entry["kind"] == cf.KIND_SOURCE
    assert entry["promote_to_release"] is False


def test_open_world_diagnostic_creates_question_and_work_order() -> None:
    diagnostic = {
        "uncertainty_label": "low_confidence",
        "candidate_work_order": {
            "prompt_excerpt": "临时用电三级配电",
            "evidence_ref_count": 0,
        },
    }
    pair = cf.work_order_from_open_world(diagnostic)
    assert pair["question_candidate"]["kind"] == cf.KIND_QUESTION
    assert pair["work_order"]["kind"] == cf.KIND_WORK_ORDER
    assert pair["work_order"]["payload"]["needs_governed_source"] is True


def test_ledger_invariants_all_separate_no_promotion() -> None:
    entries = [
        cf.make_candidate(kind=cf.KIND_ANSWER_KEY, origin="questions_bank", payload={"a": 1}),
        cf.make_candidate(kind=cf.KIND_ANSWER_KEY, origin="rag_chunk", payload={"a": 2}),
        cf.make_candidate(kind=cf.KIND_SOURCE, origin="rag_chunk", payload={"a": 3}),
    ]
    ledger = cf.build_ledger(entries)
    assert ledger["all_separate_from_release"] is True
    assert ledger["candidate_used_as_release_truth"] == 0
    assert ledger["source_laundering_blocked"] == 1


def test_source_path_conflicts_become_compiler_repair_work_orders() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    plan = general_knowledge.build_general_knowledge_query_plan("双代号网络计划总时差怎么算？")

    entries = cf.work_orders_from_source_path_conflicts(
        query_text="双代号网络计划总时差怎么算？",
        query_plan=plan,
    )

    assert entries
    assert all(entry["kind"] == cf.KIND_WORK_ORDER for entry in entries)
    assert all(entry["promote_to_release"] is False for entry in entries)
    assert any("水泥" in entry["payload"]["leaf_name_path"] for entry in entries)
    assert any(
        "source_path_conflict" in entry["payload"]["negative_evidence"]
        for entry in entries
    )
    assert entries[0]["payload"]["task"] == "repair_compiled_source_path_alignment"
