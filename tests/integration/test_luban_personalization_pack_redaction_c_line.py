"""Integration guard for C-LB1 redaction + visibility + subject isolation.

Proves: teacher-only detail (rationale / correct_answer / private internals) never
leaks into learner-visible surfaces, subject_id / user_id never cross-line, and the
PersonalizationContextPack remains the single personalization contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_learning_brain_outcome_loop_c_line as c1

pytestmark = pytest.mark.skipif(not c1.FULL100.exists(), reason="full100 graded samples absent")


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("c_line_redact")
    c1.run_c_line(out_dir=d, live_models=False)
    return d


def test_teacher_only_fields_are_redacted_from_evidence_and_cards(out):
    audit = _j(out / "redaction_and_visibility_audit_c1.json")
    assert audit["leak_in_events"] is False
    assert audit["leak_in_cards"] is False

    events = _jsonl(out / "learning_evidence_events_c1.jsonl")
    for ev in events:
        for point in ev["points"]:
            for field in c1.TEACHER_ONLY_FIELDS:
                assert field not in point

    cards_md = (out / "learner_visible_study_cards_c1.md").read_text("utf-8")
    # rationale text is teacher-only; the learner-facing card must not surface that key
    assert "rationale" not in cards_md
    assert "correct_answer" not in cards_md


def test_study_cards_answer_all_four_learner_questions(out):
    cards_md = (out / "learner_visible_study_cards_c1.md").read_text("utf-8")
    assert cards_md.count("## Card ") >= 10
    assert "扣在哪" in cards_md
    assert "为什么不能自动确认" in cards_md
    assert "下一步练什么" in cards_md
    assert "如何证明进步" in cards_md
    assert "只是 shadow" in cards_md  # shadow caveat must be visible


def test_subject_and_user_isolation(out):
    audit = _j(out / "redaction_and_visibility_audit_c1.json")
    assert audit["subject_isolation_ok"] is True
    claims = _jsonl(out / "learner_claim_projection_c1.jsonl")
    assert all(c["subject_id"] == c1.SUBJECT_ID for c in claims)

    pack_doc = _j(out / "personalization_context_pack_c1.json")
    for key, pack in pack_doc["packs"].items():
        owner = key.split("::")[0]
        assert pack["user_id"] == owner
        assert pack["subject_id"] == c1.SUBJECT_ID


def test_no_second_personalization_authority(out):
    audit = _j(out / "redaction_and_visibility_audit_c1.json")
    assert audit["second_personalization_authority"] is False
    assert audit["production_write_count"] == 0
    pack_doc = _j(out / "personalization_context_pack_c1.json")
    assert pack_doc["second_authority"] is False


def test_cross_subject_contamination_negative_control_isolated(out):
    controls = _jsonl(out / "negative_controls_c1.jsonl")
    cross = next(c for c in controls if c["control"] == "cross_subject_user_contamination")
    assert cross["isolated"] is True
    assert cross["subject_leak"] is False
    leak = next(c for c in controls if c["control"] == "teacher_only_leak")
    assert leak["redacted"] is True
    assert leak["leak_detected"] is False
