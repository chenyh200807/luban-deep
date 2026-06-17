"""Hermetic guards for the B-line QA productization sprint.

B-line consumes shadow grading outputs and builds a QA product loop. It must never:
turn a shadow score into a formal grade, route a source_gap/spec_gap to 'accept', or
leave a sample without a final disposition.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_qa_productization_b_line as b1

pytestmark = pytest.mark.skipif(
    not (b1.M9_GS_DIR / "bad_case_review_queue_m9.jsonl").exists()
    and not (b1.M8_DIR / "verified_source_candidates.jsonl").exists(),
    reason="upstream shadow supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="session", autouse=True)
def _run_b1():
    subprocess.run([sys.executable, str(b1.REPO / "scripts/run_luban_qa_productization_b_line.py")],
                   cwd=b1.REPO, check=True, capture_output=True)
    return b1.OUT_DIR


def test_at_least_50_samples_with_type_coverage():
    man = _j(b1.OUT_DIR / "qa_sample_manifest_b1.json")
    assert man["sample_total"] >= 50
    cov = man["type_coverage"]
    assert cov["source_backed_positive"] >= 10
    assert cov["high_risk"] + cov["external"] >= 10
    assert cov["source_gap"] + cov["spec_gap"] >= 10
    assert cov["override_simulation"] >= 5
    assert cov["duplicate_retry"] >= 5


def test_review_queue_is_100pct_final_disposition():
    queue = _jsonl(b1.OUT_DIR / "qa_review_queue_b1.jsonl")
    assert queue
    for row in queue:
        assert row["final_disposition"] in b1.DISPOSITIONS
        assert row["final_disposition"] != "unknown"


def test_no_gap_sample_is_routed_to_accept():
    queue = _jsonl(b1.OUT_DIR / "qa_review_queue_b1.jsonl")
    for row in queue:
        if row["final_disposition"] in ("source_gap", "spec_gap", "external_source_needed"):
            assert row["operator_action"] != "accept"
            assert row["operator_action"] in ("send_to_spec_repair", "send_to_external_source")


def test_shadow_is_never_a_formal_grade():
    queue = _jsonl(b1.OUT_DIR / "qa_review_queue_b1.jsonl")
    for row in queue:
        assert row["is_formal_score"] is False
        assert row["shadow_only"] is True


def test_operator_action_schema_is_closed_vocabulary():
    schema = _j(b1.OUT_DIR / "qa_operator_action_schema_b1.json")
    assert set(schema["actions"]) == set(b1.ACTIONS)
    for disp, act in schema["disposition_to_action"].items():
        assert disp in b1.DISPOSITIONS
        assert act in b1.ACTIONS


def test_safety_counters_are_zero():
    m = _j(b1.OUT_DIR / "qa_metrics_dashboard_snapshot_b1.json")
    assert m["bad_certified"] == 0
    assert m["source_mismatch"] == 0
    assert m["false_positive"] == 0
    assert m["production_write_count"] == 0
    assert m["legacy_equal"] is True


def test_metrics_answer_pending_override_highrisk_blocked():
    m = _j(b1.OUT_DIR / "qa_metrics_dashboard_snapshot_b1.json")
    for k in ("pending_review_rate", "override_rate", "high_risk_rate", "blocked_reason_distribution"):
        assert k in m
    assert isinstance(m["blocked_reason_distribution"], dict)
