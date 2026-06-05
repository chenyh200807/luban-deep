"""Integration guards for B-line runtime shadow safety.

The QA productization loop must never touch production: legacy construction grading is
byte-identical with/without shadow, no production runtime connection, no formal registry,
no v0 overwrite, QA-only student ids.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.run_luban_qa_productization_b_line as b1

pytestmark = pytest.mark.skipif(
    not (b1.M8_DIR / "verified_source_candidates.jsonl").exists(),
    reason="upstream shadow supply absent",
)


def _j(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


@pytest.fixture(scope="session", autouse=True)
def _run_b1():
    subprocess.run([sys.executable, str(b1.REPO / "scripts/run_luban_qa_productization_b_line.py")],
                   cwd=b1.REPO, check=True, capture_output=True)
    return b1.OUT_DIR


def test_runtime_audit_reports_legacy_unchanged_and_no_production():
    audit = _j(b1.OUT_DIR / "qa_runtime_shadow_audit_b1.json")
    assert audit["legacy_equal"] is True
    assert audit["production_runtime_connected"] is False
    assert audit["production_write_count"] == 0
    assert audit["formal_registry_emitted"] is False
    assert audit["v0_overwritten"] is False
    assert audit["qa_student_only"] is True


def test_independent_attach_shadow_keeps_legacy_byte_identical():
    """Independent re-run of the real adapter: attaching a shadow result must not mutate
    the legacy construction grading result."""
    from deeptutor.services.construction_grading.runtime_shadow_adapter import (
        LEGACY_MODE, LUBAN_AI_DRAFT_SHADOW_MODE, attach_runtime_shadow_result,
    )
    legacy = {"total_score": 4.0, "point_results": [{"point_id": "P1", "score": 4.0}], "engine": "legacy"}
    before = json.dumps(legacy, ensure_ascii=False, sort_keys=True)
    sub = {"student_id": "qa_b1_safety_0001",
           "question_followup_context": {"question_id": "Q1-NA", "question_type": "case", "user_answer": "x"}}
    legacy_only = attach_runtime_shadow_result(sub, legacy_grading_result=legacy, grading_engine_mode=LEGACY_MODE)
    with_shadow = attach_runtime_shadow_result(sub, legacy_grading_result=legacy,
                                               grading_engine_mode=LUBAN_AI_DRAFT_SHADOW_MODE)
    assert legacy_only["shadow_result"] is None
    assert json.dumps(legacy_only["legacy_grading_result"], ensure_ascii=False, sort_keys=True) == before
    assert json.dumps(with_shadow["legacy_grading_result"], ensure_ascii=False, sort_keys=True) == before


def test_gate_does_not_smuggle_shadow_into_production():
    gate = _j(b1.OUT_DIR / "qa_gated_beta_readiness_b1.json")
    assert gate["b_line_internal_gated_beta_qa_verdict"] in {"GO", "WEAK-GO", "NO-GO"}
    c = gate["constraints"]
    assert c["formal_registry_emitted"] is False
    assert c["production_runtime_connected"] is False
    assert c["v0_overwritten"] is False
    assert c["shadow_not_formal_grade"] is True


def test_blocked_input_fails_closed_to_drop():
    queue = [json.loads(line) for line in
             (b1.OUT_DIR / "qa_review_queue_b1.jsonl").read_text("utf-8").splitlines() if line.strip()]
    blocked = [q for q in queue if q["final_disposition"] == "blocked_from_writeback"]
    assert blocked, "expected at least one fail-closed blocked sample"
    for q in blocked:
        assert q["operator_action"] == "drop"
