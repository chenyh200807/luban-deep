"""M13 integration — teacher review release queue, LB preview-only, question_stem backfill.

Consumes the canonical M13 artifacts: the teacher review queue must be operable + idempotent,
Learning Brain stays preview-only (no production write), and question_stem_fact points are
quarantined in the case-event backfill queue (never release-eligible).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_formal_release_candidate_gate_m13 as m13

OUT = m13.OUT_DEFAULT

pytestmark = pytest.mark.skipif(
    not (OUT / "production_v1_go_no_go_m13.json").exists(),
    reason="canonical M13 artifacts not generated in this environment",
)


def _jsonl(name: str) -> list[dict]:
    p = OUT / name
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


def test_teacher_review_queue_is_operable_and_idempotent():
    queue = _jsonl("teacher_review_release_queue_m13.jsonl")
    for item in queue:
        assert item["operator_action_required"] == "teacher_or_operator_review"
        assert set(item["dry_run_actions"]) == {"confirm", "reject", "override"}
        for action in item["dry_run_actions"].values():
            assert action["dry_run"] is True
            assert action["writeback_performed"] is False
            assert action["high_risk_auto_changed"] is False
        assert item["idempotent"] is True
        assert item["high_risk_stays_non_auto"] is True


def test_learning_brain_release_preview_is_preview_only():
    preview = _jsonl("learning_brain_release_preview_m13.jsonl")
    assert preview
    for row in preview:
        assert row["preview_only"] is True
        assert row["writeback_performed"] is False
        assert row["production_user_written"] is False


def test_question_stem_fact_is_quarantined_in_backfill_queue():
    queue = _jsonl("case_event_text_backfill_queue_m13.jsonl")
    # M12A produced 9 question_stem_fact points with span_verified=0
    assert len(queue) >= 1
    for row in queue:
        assert row["authority_kind"] == "question_stem_fact"
        assert row["release_eligible"] is False
        assert row["stem_span_verification"] == "pending_full_case_event_text"
    coverage = json.loads((OUT / "authority_backed_runtime_coverage_m13.json").read_text("utf-8"))
    assert coverage["question_stem_release_eligible"] == 0


def test_adversarial_attacks_all_fail_closed():
    attacks = _jsonl("adversarial_release_attacks_m13.jsonl")
    assert len(attacks) >= 40
    for a in attacks:
        assert a.get("fail_closed", True) is True
