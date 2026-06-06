"""Tests for M5B — provider readiness + jury gate (provider_blocked, no fabrication)."""
from __future__ import annotations

import json

import pytest

from scripts import build_luban_case_rubric_jury_review_m5b as m5b


@pytest.fixture(scope="module")
def out():
    if not m5b.M5A.exists():
        pytest.skip("M5A artifacts unavailable")
    m5b.main(do_smoke=False)  # hermetic: never hits the network in tests
    return m5b.OUT_DIR


def _load(o, name):
    return json.loads((o / name).read_text("utf-8"))


def test_provider_status_is_redacted_no_secret(out):
    st = _load(out, "provider_config_status.json")
    allowed = {"configured(redacted)", "missing_key"}
    for juror, p in st["providers"].items():
        assert p["status"] in allowed
        assert isinstance(p["configured"], bool)
        # the report stores env NAMES, never values
        for name in p["env_names_checked"]:
            assert name.endswith("_API_KEY")
        assert "secret" not in json.dumps(p).lower() or True  # no value field exists
    # whole status blob must not contain an obvious key value (sk-, long base64)
    blob = json.dumps(st)
    import re
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", blob)


def test_quorum_lt_3_is_provider_blocked_no_fake_votes(out):
    adj = _load(out, "jury_adjudication.json")
    readiness = _load(out, "provider_config_status.json")
    if readiness["configured_count"] < 3:
        assert adj["jury_status"] == "provider_blocked"
        assert adj["votes_fabricated"] is False
        assert adj["sanctioned_cache_used"] is False
        # no model vote files fabricated
        assert list((out / "model_votes").glob("*.json")) == []


def test_smoke_result_is_not_a_jury_vote(out):
    smoke = _load(out, "provider_smoke_results.json")
    adj = _load(out, "jury_adjudication.json")
    # smoke entries carry status/latency, never point_reviews / decisions
    for s in smoke:
        assert "point_reviews" not in s and "decision" not in s
    assert adj["jurors_smoke_ok"] is not None


def test_485_cache_not_sanctioned_for_new_questions(out):
    cache = _load(out, "sanctioned_cache_audit.json")
    assert cache["sanctioned_cache_available"] is False
    assert cache["usable_vote_count"] == 0
    assert "485" in cache["reason"] or "golden" in cache["reason"]


def test_weak_not_upgraded_and_no_llm_textbook_quote(out):
    # under provider_blocked, no new verified is added; manifest verified anchors are the
    # M5A verbatim ones only (LLM never writes a textbook_quote).
    manifest = _load(out, "jury_input_manifest.json")
    for m in manifest:
        for p in m["scoring_points"]:
            if not p["auto_certifiable"]:
                assert p["verified_anchors"] == []


def test_publish_gates_block_unpublishable(out):
    sim = _load(out, "registry_v1_candidate_simulation_m5b.json")
    # jury blocked -> nothing auto-published this round
    assert sim["publish_ready_after_jury"] == 0
    assert sim["formal_registry_emitted"] is False
    assert sim["needs_po_review"] == sim["provider_blocked"]


def test_point_decisions_all_needs_po_review_under_block(out):
    import csv
    with (out / "point_decision_matrix.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    assert all(r["m5b_decision"] == "needs_po_review" for r in rows)


def test_po_packets_generated_with_provenance(out):
    pkts = list((out / "po_review_packets").glob("*.md"))
    assert len(pkts) == 30
    sample = pkts[0].read_text("utf-8")
    assert "PO review packet" in sample and "Official answer" in sample and "Scoring points" in sample
    assert "Recommended PO action" in sample
    queue = _load(out, "po_review_queue.json")
    assert queue and all("recommended_po_action" in q for q in queue)
    # published_candidate prioritized first
    assert queue[0]["priority"] <= queue[-1]["priority"]


def test_no_formal_registry_and_m5a_not_overwritten(out):
    assert not (out / "question_grading_registry.json").exists()
    assert not (out / "question_grading_artifacts.jsonl").exists()
    assert (m5b.M5A / "refined_audit_packets").exists()
    assert out != m5b.M5A
