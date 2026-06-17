"""Integration guards for the B-line teacher review + override flow.

The dangerous failures are: a mis-click 'accept' on a high-risk point granting mastery,
a non-idempotent override, or an override writing production. All must fail closed via
the REAL teacher_review_writeback (dry_run).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_qa_productization_b_line as b1

pytestmark = pytest.mark.skipif(
    not (b1.M9_GS_DIR / "bad_case_review_queue_m9.jsonl").exists(),
    reason="upstream bad-case queue absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="session", autouse=True)
def _run_b1():
    subprocess.run([sys.executable, str(b1.REPO / "scripts/run_luban_qa_productization_b_line.py")],
                   cwd=b1.REPO, check=True, capture_output=True)
    return b1.OUT_DIR


def test_override_simulation_is_idempotent():
    sim = _j(b1.OUT_DIR / "qa_review_simulation_results_b1.json")
    assert sim["summary"]["override_cases"] >= 5
    assert sim["summary"]["all_idempotent"] is True
    for r in sim["results"]:
        for sc in r["scenarios"].values():
            assert sc["idempotent"] is True


def test_teacher_misclick_accept_does_not_grant_mastery_on_high_risk():
    sim = _j(b1.OUT_DIR / "qa_review_simulation_results_b1.json")
    assert sim["summary"]["misclick_accept_blocked_for_high_risk"] is True
    for r in sim["results"]:
        # 'confirm' == teacher accepts the AI draft on a high-risk point -> never mastery
        assert r["scenarios"]["confirm"]["mastery_eligible"] is False
        assert r["scenarios"]["confirm"]["awarded_score"] == 0


def test_override_can_upgrade_and_reject_zeroes():
    sim = _j(b1.OUT_DIR / "qa_review_simulation_results_b1.json")
    for r in sim["results"]:
        assert r["scenarios"]["override"]["authority"] == "teacher_override"
        assert r["scenarios"]["override"]["mastery_eligible"] is True
        assert r["scenarios"]["reject"]["awarded_score"] == 0


def test_override_flow_writes_no_production():
    sim = _j(b1.OUT_DIR / "qa_review_simulation_results_b1.json")
    assert sim["summary"]["production_write_count"] == 0
    for r in sim["results"]:
        for sc in r["scenarios"].values():
            assert sc["dry_run"] is True


def test_teacher_packets_are_low_cost_and_sufficient():
    packet_dir = b1.PACKET_DIR
    packets = list(packet_dir.glob("*.md"))
    assert len(packets) >= 30
    # each packet must carry the three teacher-cost-reducing signals
    for p in packets[:40]:
        text = p.read_text("utf-8")
        assert "风险" in text and "证据" in text and "建议" in text
        assert "非正式分" in text  # never presented as a formal grade
