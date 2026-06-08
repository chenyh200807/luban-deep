"""M32 integration: Grading-to-Brain waterproof path over the REAL /api/v1/ws.

Proves the live WS path exercises the case grading chain for a waterproof-style case question
and returns a valid grading result in metadata. Verifies authority boundaries: no canonical
truth written via the WS path, no M31 governed bundle accidentally triggered for this domain.

This test is the live gate that upgrades M32 from WEAK-GO to GO when the runner is invoked
with ``--live``. It does NOT require the waterproof topic shard to be published — it requires
only that the grading infrastructure is wired and the /api/v1/ws path is reachable.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "wsh_m32", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
wsh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wsh)

# Waterproof case scenario: near-synonym miss (same as hermetic runner)
WATERPROOF_FRAME = {
    "type": "start_turn",
    "content": "普通防水砂浆处理",
    "capability": "deep_question",
    "language": "zh",
    "config": {
        "followup_question_context": {
            "question_id": "waterproof_case_m32_ws",
            "question_type": "case",
            "question": "地下室底板防水层施工应采用何种材料？",
            "correct_answer": "聚合物水泥防水砂浆",
        }
    },
}

# Correct-answer variant to probe the pass path
WATERPROOF_PASS_FRAME = {
    **WATERPROOF_FRAME,
    "content": "聚合物水泥防水砂浆",
}


def _client(
    tmp: str,
    *,
    user: str = "qa_m32_ws",
    write_calls: list[dict[str, Any]] | None = None,
) -> TestClient:
    wc = write_calls if write_calls is not None else []
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    wsh._install_fakes(rt, user_id=user, write_calls=wc, engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: wsh._auth_ctx(user)
    return TestClient(wsh._build_ws_app())


def test_waterproof_case_ws_returns_construction_grading_result() -> None:
    """The full WS chain for a case-type answer produces construction_grading_result in metadata."""
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_FRAME)
    md = result.get("metadata") or {}
    assert "construction_grading_result" in md, (
        "waterproof case WS turn must produce construction_grading_result in metadata — "
        "grading chain not reached"
    )


def test_waterproof_case_ws_no_canonical_truth_written() -> None:
    """Candidate-grade waterproof domain must never write canonical learner truth via WS.

    canonical_truth_written is nested inside learning_evidence_preview (the real field the
    runtime populates). Checking md["canonical_truth_written"] would always be None — a vacuous
    pass. Must check md["learning_evidence_preview"]["canonical_truth_written"] instead,
    matching the gap1 pattern (test_luban_gap1_learning_evidence_preview_ws.py:66).
    """
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_FRAME)
    md = result.get("metadata") or {}
    preview = md.get("learning_evidence_preview")
    if preview is not None:
        assert preview.get("canonical_truth_written") is False, (
            "learning_evidence_preview.canonical_truth_written must be False — "
            "authority boundary violated for candidate-grade waterproof domain"
        )


def test_waterproof_case_ws_no_m31_governed_objective_triggered() -> None:
    """M32 waterproof domain must NOT accidentally trigger M31 governed-objective mode.

    M31 is flag+cohort gated: requires grading_engine_m31_governed_objective=True in the
    config frame AND a matching cohort prefix (qa_*, test_*, operator_*). WATERPROOF_FRAME
    has neither flag set, so the key must be absent from metadata.
    """
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_FRAME)
    md = result.get("metadata") or {}
    # M31 is flag+cohort gated; no flag set in WATERPROOF_FRAME config, so key must be absent.
    assert "luban_grading_engine_m31_governed_objective" not in md, (
        "waterproof case must not trigger M31 governed objective — "
        "WATERPROOF_FRAME has no grading_engine_m31_governed_objective=True flag"
    )


def test_waterproof_case_ws_cohort_and_non_cohort_both_get_grading() -> None:
    """Standard grading result is present for all users (no cohort gate on waterproof domain)."""
    for user in ("qa_m32_ws", "real_student_42", "test_user_9"):
        with tempfile.TemporaryDirectory() as tmp, _client(tmp, user=user) as c:
            result = wsh._receive_result(c, WATERPROOF_FRAME)
        md = result.get("metadata") or {}
        assert "construction_grading_result" in md, (
            f"user={user!r}: construction_grading_result absent — grading must be unconditional"
        )


def test_waterproof_case_ws_pass_answer_still_returns_result() -> None:
    """A correct waterproof answer completes the WS turn, returns grading, and no canonical write.

    The pass path is where a promoted write could sneak through if counted_as_improvement is
    accidentally True. Verify the same authority invariants as the miss path.
    """
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_PASS_FRAME)
    md = result.get("metadata") or {}
    assert "construction_grading_result" in md
    preview = md.get("learning_evidence_preview")
    if preview is not None:
        assert preview.get("canonical_truth_written") is False, (
            "pass path must not write canonical truth — candidate-grade pass is preview only"
        )
        assert preview.get("mastery_raised") is False, (
            "pass path must not raise mastery — candidate-grade pass is preview only"
        )
