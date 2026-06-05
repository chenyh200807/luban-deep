"""Hermetic guards for M9 v1 beta shadow grand sprint.

M9 promotes the Luban grading engine to an evaluable ``beta_shadow_candidate``:
source expansion (deterministic verbatim exact-match is the only source authority)
-> beta compiler -> runtime shadow -> QA product slice -> Learning-Brain loop.
It must not emit a formal registry, overwrite v0, connect production runtime, call
live models by default, or treat official answers / model votes / council votes as
textbook source.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.run_luban_v1_beta_shadow_grand_sprint_m9 as m9

pytestmark = pytest.mark.skipif(
    not (m9.M8 / "verified_source_candidates.jsonl").exists()
    or not m9.FULL100.exists(),
    reason="M8 / full100 inputs absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _dir_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(file.relative_to(path)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def m9_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m9_beta")
    result = m9.run_m9(out_dir=out, live_models=False, max_rounds=3)
    return out, result


def test_workflow_ledger_records_all_six_patterns(m9_run):
    out, _ = m9_run
    ledger = _j(out / "workflow_ledger_m9.json")
    assert set(ledger) == {
        "classify_and_act", "fanout_and_synthesize", "adversarial_verification",
        "generate_and_filter", "tournament", "loop_until_done",
    }
    for spec in ledger.values():
        assert (out / spec["evidence_file"]).exists()


def test_model_usage_plan_makes_no_live_calls_by_default(m9_run):
    out, _ = m9_run
    plan = _j(out / "model_usage_plan_m9.json")
    assert plan["live_calls_requested"] is False
    assert plan["live_calls_performed"] is False
    assert plan["deterministic_source_gate_is_authority"] is True
    assert all(v == 0 for v in plan["actual_calls"].values())
    assert all(m["max_calls"] == 0 for m in plan["models"])


def test_source_expansion_is_textbook_anchored_and_adversarially_clean(m9_run):
    out, _ = m9_run
    inventory = _j(out / "source_expansion_inventory.json")
    verified = _jsonl(out / "verified_source_candidates_m9.jsonl")
    adversarial = _jsonl(out / "adversarial_source_reviews_m9.jsonl")
    delta = _j(out / "source_coverage_delta.json")

    # M5D approve_with_repaired_anchor == M7 council-safe set, already in baseline -> 0 new.
    assert inventory["baseline_carry_forward"] == 18
    assert inventory["new_track_source_backed_total"] == 18
    assert inventory["m9_new_source_backed"] == 0
    assert delta["m9_new_track_source_backed_total"] == 18

    assert len(verified) == 18
    assert all(v["source_authority"] == "textbook_exact_match" for v in verified)
    assert all(v.get("verified_source_ref", {}).get("textbook_exact_match") is True for v in verified)

    promotions = [r for r in adversarial if r.get("stage") == "beta_promotion"]
    assert len(promotions) == 18
    assert all(r["survives"] for r in promotions)
    assert all(r["evidence_verbatim_textbook"] for r in promotions)
    assert all(r["adversarial_checks"]["official_answer_disguised_as_textbook"] is False for r in promotions)
    assert all(r["adversarial_checks"]["model_vote_as_source"] is False for r in promotions)
    assert all(r["adversarial_checks"]["council_vote_as_source"] is False for r in promotions)


def test_beta_compiler_is_candidate_only_and_does_not_overwrite_v0(m9_run, tmp_path):
    out, _ = m9_run
    registry = _j(out / "registry_v1_beta_shadow_candidate.json")
    audit = _j(out / "compiler_gate_audit_m9.json")
    runtime = _j(out / "runtime_shadow_gate_preview_m9.json")

    assert registry["status"] == m9.BETA_STATUS
    assert registry["formal_registry_emitted"] is False
    assert registry["production_runtime_connected"] is False
    assert registry["v0_overwritten"] is False
    assert registry["human_reviewed"] is False
    assert registry["expansion_track"]["new_track_source_backed_total"] == 18
    # beta candidate registry = v0 textbook backbone (read-only) + new expansion track
    assert registry["beta_shadow_total_auto_preview"] == registry["backbone"]["v0_textbook_auto_points"] + 18

    for key in ("official_answer_upgraded_to_textbook", "model_vote_upgraded_to_textbook",
                "council_vote_upgraded_to_textbook", "source_mismatch", "list_rule_partial_anchor_auto"):
        assert audit[key] == 0
    assert audit["all_new_points_textbook_anchored"] is True

    assert runtime["production_runtime_connected"] is False
    assert runtime["auto_certified_in_production"] == 0
    assert not (out / "registry_v1.json").exists()
    assert not (out / "question_grading_registry_v1.json").exists()


def test_v0_directory_is_read_only(tmp_path):
    before = _dir_digest(m9.V0)
    m9.run_m9(out_dir=tmp_path / "fresh", live_models=False)
    assert _dir_digest(m9.V0) == before


def test_eval_summary_invariants_are_all_zero_and_legacy_unchanged(m9_run):
    out, _ = m9_run
    summary = _j(out / "beta_shadow_eval_summary_m9.json")
    assert summary["bad_certified"] == 0
    assert summary["source_mismatch"] == 0
    assert summary["official_answer_as_textbook"] == 0
    assert summary["model_vote_as_source"] == 0
    assert summary["list_rule_partial_anchor_auto"] == 0
    assert summary["live_calls"] == 0
    assert summary["legacy_output_unchanged"] is True
    # the model-shadow self-certified points that are not yet source-backed are a residual
    # repair queue, not a violation; they must be surfaced rather than silently dropped.
    assert summary["residual_source_repair_queue"] >= 0


def test_runtime_shadow_does_not_overwrite_legacy(m9_run):
    out, _ = m9_run
    audit = _j(out / "runtime_shadow_legacy_unchanged_m9.json")
    assert audit["legacy_equal"] is True
    assert audit["legacy_key_overwritten"] is False
    assert audit["shadow_attached"] is True
    assert audit["production_runtime_connected"] is False


def test_verdict_and_finding(m9_run):
    out, result = m9_run
    assert result["verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    assert result["verdict"] == "WEAK-GO"  # new-track 18 in [18,49], all invariants pass
    assert result["invariants_all_pass"] is True
    assert result["study_cards"] >= 10
    finding = (out / "M9_FINDING_v1_beta_shadow_grand_sprint_20260604.md").read_text("utf-8")
    for idx in range(1, 13):
        assert f"{idx}." in finding
    assert "production_runtime_connected=false" in finding
    assert "legacy unchanged" in finding
    assert "official_answer" in finding
    assert "beta_shadow 非正式分数" in finding


def test_build_beta_shadow_grading_view_is_append_only():
    legacy = {"event": "RESULT", "metadata": {
        "construction_grading_result": {"score_awarded": 2, "max_score": 4, "authority": "CaseGradingSkillKernel"}}}
    import copy
    before = copy.deepcopy(legacy)
    out = m9.build_beta_shadow_grading_view(legacy, {"registry_status": m9.BETA_STATUS}, enabled=True)
    assert legacy == before  # caller payload not mutated
    assert out["metadata"]["construction_grading_result"] == before["metadata"]["construction_grading_result"]
    shadow = out["metadata"][m9.SHADOW_KEY]
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert shadow["production_runtime_connected"] is False
    assert shadow["human_reviewed"] is False
    assert shadow["scores"]["legacy_score_overwritten"] is False


def test_build_beta_shadow_grading_view_can_be_disabled():
    legacy = {"event": "RESULT", "metadata": {
        "construction_grading_result": {"score_awarded": 0, "max_score": 3, "authority": "CaseGradingSkillKernel"}}}
    out = m9.build_beta_shadow_grading_view(legacy, {"registry_status": m9.BETA_STATUS}, enabled=False)
    assert out == legacy
    assert m9.SHADOW_KEY not in out["metadata"]
