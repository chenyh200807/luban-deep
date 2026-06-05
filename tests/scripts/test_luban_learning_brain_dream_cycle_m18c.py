"""Hermetic guards for M18C Learning Brain Dream Cycle + PCP Shadow Ops.

The dream cycle consumes M17A / C-LB1 grading evidence into evidence -> claim ->
PersonalizationContextPack -> next-action / retest -> dream-lint, all dry-run. It must
never write production / canonical truth, never promote shadow to mastery, never build a
second personalization authority, and must keep training_intent as the sole prescription
authority.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_dream_cycle_m18c as m18c

pytestmark = pytest.mark.skipif(
    not (m18c.M17A / "learning_brain_event_drafts_m17a.jsonl").exists(),
    reason="M17A runtime event drafts absent",
)


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m18c")
    result = m18c.run_m18c(out_dir=out)
    return out, result


def test_required_artifacts_exist(run):
    out, _ = run
    for name in (
        "workflow_ledger_m18c.json", "evidence_draft_inventory_m18c.json",
        "claim_lifecycle_projection_m18c.jsonl", "personalization_context_packs_m18c.jsonl",
        "next_action_tournament_m18c.json", "retest_plan_candidates_m18c.jsonl",
        "dream_cycle_lint_candidates_m18c.jsonl", "unsupported_claim_audit_m18c.json",
        "leakage_and_authority_attack_results_m18c.json", "learning_brain_quality_metrics_m18c.json",
        "production_write_guard_m18c.json", "FINDING_learning_brain_dream_cycle_m18c_20260604.md",
    ):
        assert (out / name).exists(), name


def test_workflow_ledger_has_six_patterns(run):
    out, _ = run
    ledger = _j(out / "workflow_ledger_m18c.json")
    assert set(ledger) == {
        "classify_and_act", "fanout_and_synthesize", "generate_and_filter",
        "tournament", "adversarial_verification", "loop_until_done",
    }


def test_evidence_ingested_from_m17a_and_clb1(run):
    out, _ = run
    inv = _j(out / "evidence_draft_inventory_m18c.json")
    assert inv["evidence_drafts_read"] >= 20
    assert inv["by_source"].get("m17a_runtime_llm_adjudication", 0) >= 1
    assert set(inv["by_bucket"]) <= set(m18c.CLASSIFY_BUCKETS)


def test_hard_metrics_all_pass(run):
    out, result = run
    assert result["all_safe"] is True
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    m = result["metrics"]
    assert m["shadow_promoted_to_mastery"] == 0
    assert m["simulated_retest_as_real"] == 0
    assert m["unsupported_claim_rate"] == 0.0
    assert m["evidence_coverage"] >= 0.95
    assert m["generic_fallback_rate"] <= 0.05
    assert m["cross_user_leak"] == 0
    assert m["subject_leak"] == 0
    assert m["teacher_only_leak"] == 0
    assert m["second_memory_authority"] is False
    assert m["second_rag_authority"] is False
    assert m["personalization_context_contract_unique"] is True


def test_production_write_guard(run):
    out, _ = run
    guard = _j(out / "production_write_guard_m18c.json")
    assert guard["production_write_count"] == 0
    assert guard["canonical_truth_written"] is False
    assert guard["any_claim_promoted_to_mastery"] is False
    assert guard["any_canonical_truth_written"] is False
    assert guard["any_human_field_written"] is False
    assert guard["grading_runtime_touched"] is False
    assert guard["new_db_schema"] is False
    assert guard["second_personalization_authority"] is False


def test_pcps_isolated_by_user_and_subject_with_evidence_refs(run):
    out, _ = run
    pcps = _jsonl(out / "personalization_context_packs_m18c.jsonl")
    assert len(pcps) >= 1
    seen = set()
    for p in pcps:
        assert p["contract"] == m18c.PERSONALIZATION_CONTRACT
        assert p["is_second_memory_authority"] is False
        assert p["is_second_personalization_authority"] is False
        assert p["canonical_mastery_claims"] == []
        assert p["prescription_authority"] == "training_intent"
        assert p["evidence_refs"]            # every PCP carries evidence refs
        assert p["supporting_event_ids"]     # and supporting event ids
        key = (p["user_id"], p["subject_id"])
        assert key not in seen               # one pack per (user, subject)
        seen.add(key)


def test_claims_never_promoted_to_canonical_mastery(run):
    out, _ = run
    claims = _jsonl(out / "claim_lifecycle_projection_m18c.jsonl")
    assert claims
    for c in claims:
        assert c["promoted_to_canonical_mastery"] is False
        assert c["canonical_truth_written"] is False
        assert c["production_write_performed"] is False
        assert c["human_reviewed"] is False
        assert c["final_disposition"] in m18c.FINAL_DISPOSITIONS
        assert c["supporting_event_ids"]     # unsupported_claim_rate=0 invariant


def test_next_action_built_on_training_intent_not_second_authority(run):
    out, _ = run
    tournament = _j(out / "next_action_tournament_m18c.json")
    assert tournament["prescription_authority"] == "training_intent"
    assert tournament["ranking_view_is_not_authority"] is True
    # selected variant must never be the overclaim one
    for row in tournament["tournament"]:
        assert row["selected"] != "C_overclaim"


def test_dream_cycle_emits_candidates_not_silent_rewrites(run):
    out, _ = run
    lint = _jsonl(out / "dream_cycle_lint_candidates_m18c.jsonl")
    assert lint
    kinds = {x["candidate_kind"] for x in lint}
    assert kinds <= {"unsupported_claim", "stale_or_unconfirmed_claim", "contradicted_claim",
                     "missing_retest", "missing_next_action"}
    for x in lint:
        assert x["silent_rewrite"] is False


def test_retest_plans_mark_simulation_not_proof(run):
    out, _ = run
    plans = _jsonl(out / "retest_plan_candidates_m18c.jsonl")
    assert plans
    for p in plans:
        assert p["real_retest_required"] is True
        assert p["simulation_is_not_proof"] is True
        assert p["production_write_performed"] is False


def test_finding_answers_twelve_questions(run):
    out, _ = run
    finding = (out / "FINDING_learning_brain_dream_cycle_m18c_20260604.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "training_intent" in finding
    assert "shadow" in finding
