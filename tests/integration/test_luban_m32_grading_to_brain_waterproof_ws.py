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
    """Candidate-grade waterproof domain must never write canonical learner truth via WS."""
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_FRAME)
    md = result.get("metadata") or {}
    assert not md.get("canonical_truth_written"), (
        "WS path must not write canonical truth for candidate-grade domain — "
        "authority boundary violated"
    )


def test_waterproof_case_ws_no_m31_governed_objective_triggered() -> None:
    """M32 waterproof domain must NOT accidentally trigger M31 governed-objective mode."""
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_FRAME)
    md = result.get("metadata") or {}
    assert "luban_grading_engine_m31_governed_objective" not in md, (
        "waterproof case must not trigger M31 governed objective — wrong authority lane"
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
    """A correct waterproof answer also completes the WS turn and returns a grading result."""
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        result = wsh._receive_result(c, WATERPROOF_PASS_FRAME)
    md = result.get("metadata") or {}
    assert "construction_grading_result" in md
