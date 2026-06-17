"""M5R provider-readiness + sanctioned-rerun invariants.

Core behavior tests use build_m5 with injected vote functions (no live providers); artifact
tests read the readiness dir when present. No secrets, no fabrication, no formal registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_case_rubric_jury_review_m5 import build_m5, M4_DIR
import scripts.run_luban_case_rubric_jury_review_m5r as m5r

REPO = Path(__file__).resolve().parents[2]
READY = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_provider_readiness_m5r_20260604"
needs_m4 = pytest.mark.skipif(not (M4_DIR / "jury_review_packets").exists(), reason="M4 packets absent")
needs_ready = pytest.mark.skipif(not READY.exists(), reason="readiness artifacts absent")


@needs_m4
def test_fewer_than_3_models_blocks_adjudication(tmp_path):
    def two(model, packet):  # only 2 real models -> quorum (3) not met
        if model in ("a", "b"):
            return {"model": model, "reviewer_type": "llm_jury", "votes_fabricated": False,
                    "point_reviews": [{"point_id": p["point_id"], "decision": "accept",
                                       "missing_point_risk": "low"} for p in packet["scoring_point_candidates"]],
                    "question_level_decision": "publish_candidate"}
        return {"model": model, "status": "provider_unavailable", "votes_fabricated": False}
    r = build_m5(tmp_path, vote_fn=two, models=["a", "b", "gpt55"])
    assert r["sim"]["quorum_blocked"] == r["manifest"]["input_packets"]
    assert r["sim"]["publish_ready_after_jury"] == 0


@needs_m4
def test_three_mocked_models_enter_rerun_path(tmp_path):
    def three(model, packet):  # 3 real accepting models -> quorum met, adjudication runs
        return {"model": model, "reviewer_type": "llm_jury", "votes_fabricated": False,
                "point_reviews": [{"point_id": p["point_id"], "decision": "accept",
                                   "missing_point_risk": "low"} for p in packet["scoring_point_candidates"]],
                "question_level_decision": "publish_candidate"}
    r = build_m5(tmp_path, vote_fn=three, models=["m1", "m2", "m3"])
    assert r["sim"]["quorum_blocked"] == 0  # all reach quorum
    decided = (r["sim"]["publish_ready_after_jury"] + r["sim"]["draft_after_jury"]
               + r["sim"]["needs_po_review"] + r["sim"]["rejected"])
    assert decided == r["manifest"]["input_packets"]


@needs_m4
def test_fabricated_votes_rejected(tmp_path):
    def fab(model, packet):
        return {"model": model, "votes_fabricated": True, "point_reviews": []}
    with pytest.raises(AssertionError):
        build_m5(tmp_path, vote_fn=fab, models=["m1", "m2", "m3"])


@needs_m4
def test_provider_unavailable_recorded_not_skipped(tmp_path):
    r = build_m5(tmp_path, vote_fn=lambda m, p: {"model": m, "status": "provider_unavailable",
                                                 "votes_fabricated": False}, models=["m1", "m2", "m3"])
    assert all(c == r["manifest"]["input_packets"] for c in r["provider_unavailable"].values())
    assert list((tmp_path / "model_votes").glob("*__provider_unavailable.json"))
    assert r["sim"]["registry_emitted"] is False


def test_real_vote_fn_unavailable_models_fail_closed():
    # gpt55/opus48 have no live mapping -> provider_unavailable, never fabricated
    v = m5r.real_vote_fn("gpt55", {"question_id": "Q", "scoring_point_candidates": []})
    assert v["status"] == "provider_unavailable"
    assert v["votes_fabricated"] is False


@needs_ready
def test_provider_config_status_has_no_secret_values():
    doc = json.loads((READY / "provider_config_status.json").read_text("utf-8"))
    assert doc.get("secrets_printed") is False
    blob = json.dumps(doc, ensure_ascii=False)
    # no opaque token-like values: every string value is a bool/url/model_id/known label
    assert "sk-" not in blob  # no OpenAI-style key prefix leaked
    assert doc["minimum_quorum_possible"] in (True, False)


@needs_ready
def test_sanctioned_cache_rejects_485_and_requires_exact_match():
    sca = json.loads((READY / "sanctioned_cache_audit.json").read_text("utf-8"))
    assert sca["sanctioned_cache_available"] is False
    assert sca["485_cache_explicitly_forbidden_for_new_questions"] is True


@needs_ready
def test_smoke_results_are_not_jury_votes():
    smoke = json.loads((READY / "provider_smoke_results.json").read_text("utf-8"))
    for r in smoke["results"]:
        assert "point_reviews" not in r  # a smoke is not a vote
        assert "decision" not in r


@needs_ready
def test_rerun_command_points_to_real_script():
    txt = (READY / "rerun_command.md").read_text("utf-8")
    assert "scripts.run_luban_case_rubric_jury_review_m5r" in txt
    assert (REPO / "scripts/run_luban_case_rubric_jury_review_m5r.py").exists()


@needs_ready
def test_readiness_dir_has_no_formal_registry():
    assert not (READY / "registry_v1.json").exists()
    assert not (READY / "question_grading_registry.json").exists()
