"""Hermetic guards for M13D teacher review ops hardening."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_teacher_review_ops_hardening_m13d as m13d

pytestmark = pytest.mark.skipif(
    not (m13d.B_QA1 / "qa_review_queue_b1.jsonl").exists(),
    reason="B-QA1 review queue absent",
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="module")
def m13d_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("m13d")
    result = m13d.run_m13d(out)
    return out, result


def test_review_queue_has_100pct_final_disposition(m13d_run):
    out, result = m13d_run
    metrics = _json(out / "operator_metrics_m13d.json")
    queue = _jsonl(out / "review_queue_consolidated_m13d.jsonl")
    assert result["queue_count"] == len(queue)
    assert metrics["review_queue_100pct_final_disposition"] is True
    assert metrics["unknown_disposition"] == 0


def test_teacher_packets_cover_queue_or_at_least_50(m13d_run):
    out, _ = m13d_run
    queue = _jsonl(out / "review_queue_consolidated_m13d.jsonl")
    packets = sorted((out / "teacher_packets_m13d").glob("*.md"))
    assert len(packets) == len(queue)
    assert len(packets) >= 50 or len(packets) == len(queue)
    sample = packets[0].read_text("utf-8")
    assert "Non-formal score" in sample
    assert "Blocked reason" in sample
    assert "Can override" in sample


def test_confirm_reject_override_dryrun_idempotent(m13d_run):
    out, _ = m13d_run
    actions = _jsonl(out / "teacher_action_dryrun_m13d.jsonl")
    assert {"confirm", "reject", "override", "mistaken_accept_high_risk"} <= {row["action"] for row in actions}
    confirm_hashes: dict[str, set[str]] = {}
    for row in actions:
        assert row["dry_run"] is True
        assert row["production_write_count"] == 0
        if row["action"] == "confirm":
            confirm_hashes.setdefault(row["queue_id"], set()).add(row["action_hash"])
    assert confirm_hashes
    assert all(len(values) == 1 for values in confirm_hashes.values())


def test_mistaken_high_risk_accept_guard_blocks_mastery_and_auto(m13d_run):
    out, _ = m13d_run
    guard = _json(out / "mistaken_accept_guard_audit_m13d.json")
    assert guard["guarded_attempts"] > 0
    assert guard["mistaken_high_risk_accept_blocked"] is True
    assert guard["high_risk_or_source_gap_auto_promoted"] == 0
    assert guard["mastery_written"] == 0


def test_no_production_or_authority_mutation(m13d_run):
    out, _ = m13d_run
    manifest = _json(out / "teacher_review_ops_manifest_m13d.json")
    metrics = _json(out / "operator_metrics_m13d.json")
    assert manifest["touches_scoring_authority"] is False
    assert manifest["touches_runtime"] is False
    assert metrics["production_write_count"] == 0
    assert metrics["lb_canonical_writeback"] == 0
    assert metrics["source_authority_mutation"] is False


def test_finding_answers_limited_release_blocker(m13d_run):
    out, _ = m13d_run
    finding = (out / "FINDING_teacher_review_ops_hardening_m13d_20260604.md").read_text("utf-8")
    assert "queue 是否可用" in finding
    assert "老师操作成本" in finding
    assert "M13/M14 limited release" in finding
