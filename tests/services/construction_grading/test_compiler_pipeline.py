"""Living LLM Artifact Compiler deterministic pipeline spine tests."""
from __future__ import annotations

from deeptutor.services.construction_grading import compiler_feedback as CF
from deeptutor.services.construction_grading import compiler_pipeline as P
from deeptutor.services.construction_grading import feedback_ingest_bridge as B
from deeptutor.services.construction_grading import full_knowledge_compiler as FKC


def _machine_spec_evidence() -> dict:
    return B.make_evidence_item(
        evidence_kind="machine_spec_point",
        payload={
            "point_id": "Q1::P1",
            "question_id": "Q1",
            "text": "工期顺延 25 天",
            "machine_spec": {"kind": "machine_checkable_calc", "expected": 25},
            "required_terms": ["顺延"],
        },
        run_id="test-run",
    )


def test_pipeline_signs_machine_spec_only_at_s5_and_safety_stays_clean():
    result = P.run_pipeline([_machine_spec_evidence()], run_id="test-run", max_iter=1)

    bundle = result["signed_bundle"]
    assert bundle is not None
    assert FKC.verify_lane_bundle(bundle, "case_rubric_full") is True
    assert result["promoted_count"] == 1
    assert result["safety"]["candidate_used_as_release_truth"] == 0
    assert result["safety"]["illegit_promote_outside_s5"] == 0
    assert result["safety"]["published"] is False
    assert result["safety"]["production_write_count"] == 0

    promoted = [c for c in result["candidates"] if c.get("promote_to_release") is True]
    assert len(promoted) == 1
    assert any(entry.get("stage") == "S5" for entry in promoted[0]["stage_log"])


def test_pipeline_routes_invalid_spec_to_work_order_without_signing():
    bad = B.make_evidence_item(
        evidence_kind="machine_spec_point",
        payload={"point_id": "Q1::P1", "question_id": "Q1", "text": "missing spec"},
        run_id="test-run",
    )
    result = P.run_pipeline([bad], run_id="test-run", max_iter=1)

    assert result["signed_bundle"] is None
    assert result["promoted_count"] == 0
    assert len(result["work_orders"]) == 1
    assert result["work_orders"][0]["stage_log"][-1]["gate"] == "G4_spec_attack"


def test_pipeline_laundering_attempt_is_rejected_at_birth():
    evidence = B.make_evidence_item(
        evidence_kind="retrieval_chunk",
        payload={"chunk_id": "rag-1", "content": "A"},
        run_id="test-run",
    )

    def rogue_worker(_item: dict) -> list[dict]:
        return [
            CF.make_candidate(
                kind=CF.KIND_ANSWER_KEY,
                origin="rag_chunk",
                payload={"question_id": "Q1", "answer_key": "A"},
            )
        ]

    result = P.run_pipeline([evidence], run_id="test-run", llm_worker=rogue_worker, max_iter=1)

    assert result["signed_bundle"] is None
    assert result["promoted_count"] == 0
    assert result["safety"]["source_laundering_blocked"] == 1
    assert result["safety"]["candidate_used_as_release_truth"] == 0
    assert result["rejected"][0]["kind"] == CF.KIND_REJECTED
