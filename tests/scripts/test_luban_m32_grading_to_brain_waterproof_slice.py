"""M32 Task 1/7: the end-to-end waterproof slice runner must drive the whole
Grading-to-Brain loop with hermetic fixtures, emit every required artifact, attest ONLY what
it actually exercises (verified-in-this-run vs not-exercised), prove the SAFETY direction of
the authority gate, and render an HONEST verdict — WEAK-GO, because canonical promotion on a
candidate-grade topic is not demonstrable hermetically."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "m32_slice", REPO / "scripts" / "run_luban_m32_grading_to_brain_waterproof_slice.py"
)
m32 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m32)

REQUIRED = [
    "waterproof_topic_manifest_m32.json", "compiled_context_consumption_m32.json",
    "grading_event_ledger_m32.jsonl", "learning_evidence_ledger_m32.jsonl",
    "learner_claim_projection_m32.jsonl", "personalization_context_pack_m32.json",
    "next_best_action_m32.json", "retest_outcome_proof_m32.jsonl",
    "teacher_final_real_retest_promotion_m32.json",
    "safety_invariant_report_m32.json", "go_no_go_m32.json",
]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_slice_emits_all_required_artifacts_and_honest_weak_go(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    for name in REQUIRED:
        assert (tmp_path / name).exists(), f"missing artifact {name}"
    assert list(tmp_path.glob("FINDING_grading_to_brain_m32_waterproof_*.md")), "missing FINDING"
    gng = json.loads((tmp_path / "go_no_go_m32.json").read_text(encoding="utf-8"))
    # Hermetic run: live /api/v1/ws not exercised → WEAK-GO per plan §313.
    assert gng["verdict"] == "WEAK-GO"
    assert gng["mode"] == "hermetic_only"
    assert gng["safety_gate_proven"] is True
    assert gng["live_ws_exercised"] is False
    assert gng["canonical_promotion_demonstrated"] is True
    assert gng["live_blockers"]
    # live_ws gate must be present in live_blockers when not exercised
    assert any("live /api/v1/ws" in b for b in gng["live_blockers"])


def test_live_ws_gate_upgrades_verdict_to_go(tmp_path) -> None:
    """When live_ws_exercised=True (--live path passed integration test), verdict becomes GO."""
    m32.run_slice(out_dir=str(tmp_path), live_ws_exercised=True)
    gng = json.loads((tmp_path / "go_no_go_m32.json").read_text(encoding="utf-8"))
    assert gng["verdict"] == "GO", (
        f"live_ws_exercised=True should produce GO per plan §312; got {gng['verdict']}"
    )
    assert gng["mode"] == "live_ws_exercised"
    assert gng["live_ws_exercised"] is True
    assert gng["safety_gate_proven"] is True
    assert gng["canonical_promotion_demonstrated"] is True
    # live_ws blocker must be absent when exercised
    assert not any("live /api/v1/ws not exercised" in b for b in gng["live_blockers"])


def test_safety_report_attests_only_what_it_exercises(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    report = json.loads((tmp_path / "safety_invariant_report_m32.json").read_text(encoding="utf-8"))
    v = report["verified_in_this_run"]
    assert report["verified_clean"] is True
    # the invariants this slice genuinely derives are clean
    assert v["canonical_truth_written"] is False
    assert v["production_write_count"] == 0
    assert v["simulated_retest_as_real"] == 0
    assert v["shadow_promoted_to_mastery"] == 0
    assert v["candidate_used_as_release_truth"] == 0
    assert v["candidate_shard_published"] == 0
    assert v["candidate_official_score_allowed"] == 0
    assert v["candidate_status_allowed"] is True
    assert v["candidate_grade_pass_promoted"] == 0
    assert v["caller_scoping_ok"] is True
    # laundering / cross-tenant / positive-arm are NAMED as not-exercised, never stamped clean here
    ne = report["not_exercised_in_this_slice"]
    for key in ("official_score_laundering", "answer_key_override", "source_laundering", "rag_chunk_as_answer_key"):
        assert ne.get(key), f"{key} must be explicitly marked not-exercised, not silently 0"


def test_published_candidate_shard_forces_no_go(tmp_path, monkeypatch) -> None:
    fake_repo = tmp_path / "repo"
    shard_path = fake_repo / m32.SHARD_REL
    shard_path.parent.mkdir(parents=True)
    shard = json.loads((REPO / m32.SHARD_REL).read_text(encoding="utf-8"))
    shard["manifest"]["published"] = True
    shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(m32, "REPO", fake_repo)

    m32.run_slice(out_dir=str(tmp_path / "out"))
    gng = json.loads((tmp_path / "out" / "go_no_go_m32.json").read_text(encoding="utf-8"))
    v = gng["safety_verified_in_this_run"]
    assert gng["verdict"] == "NO-GO"
    assert gng["verified_clean"] is False
    assert v["candidate_shard_published"] == 1
    assert v["candidate_used_as_release_truth"] == 1


def test_authority_gate_safety_direction(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    proofs = _jsonl(tmp_path / "retest_outcome_proof_m32.jsonl")
    by_auth = {p["authority"]: p for p in proofs}
    assert by_auth["candidate_preview"]["counted_as_improvement"] is False
    assert by_auth["simulated"]["counted_as_improvement"] is False
    assert by_auth["simulated"]["simulated"] is True


def test_teacher_final_real_retest_positive_arm_is_demonstrated(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    proof = json.loads((tmp_path / "teacher_final_real_retest_promotion_m32.json").read_text(encoding="utf-8"))

    assert proof["teacher_final_confirmed_claim"]["claim_status"] == "confirmed"
    assert proof["teacher_final_confirmed_claim"]["evidence_level"] == "L2_confirmed"
    assert proof["real_retest"]["counted_as_improvement"] is True
    assert proof["post_retest_projection"]["weak_points"] == []
    assert proof["post_retest_projection"]["stale_claims"][0]["claim_status"] == "stale"
    assert proof["personalization_context_after_teacher_final"]["next_best_action_candidates"]


def test_loop_is_explainable_end_to_end(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    evidence = _jsonl(tmp_path / "learning_evidence_ledger_m32.jsonl")
    assert evidence
    hits = evidence[0]["rubric"]["scoring_point_hits"]
    assert hits and hits[0].get("mistake_type") and hits[0].get("evidence_span")
    # evidence is preview (candidate authority threaded through the real consumer)
    assert evidence[0].get("preview_only") is True
    assert evidence[0].get("canonical_truth_written") is False
    claims = _jsonl(tmp_path / "learner_claim_projection_m32.jsonl")
    assert claims and any(c.get("evidence_span") for c in claims)
    nba = json.loads((tmp_path / "next_best_action_m32.json").read_text(encoding="utf-8"))
    assert nba.get("action_type") and nba.get("target") and nba.get("success_measure")


def test_topic_manifest_points_to_unpublished_signed_shard(tmp_path) -> None:
    m32.run_slice(out_dir=str(tmp_path))
    manifest = json.loads((tmp_path / "waterproof_topic_manifest_m32.json").read_text(encoding="utf-8"))
    assert manifest["published"] is False
    assert manifest["official_score_allowed"] is False
    assert manifest["status"] in {"release_candidate", "draft"}
    assert manifest["content_hash"] and manifest["signature"]
    assert manifest["canonical_pointer"].endswith("v_topic_waterproof/topic_waterproof.json")
