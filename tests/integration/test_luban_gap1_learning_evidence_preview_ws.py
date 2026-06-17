"""gap_1 / M28 integration: a REAL /api/v1/ws grading conversation must drive
``build_learning_evidence_from_context_pack`` and append a learning_evidence preview.

This is the production-coverage proof: the Learning-Brain consumer was previously
reachable only from offline scripts/tests (live calls = 0). Here a real grading turn
goes through TurnRuntimeManager -> ChatOrchestrator -> DeepQuestionCapability and the
preview shows up in the live result payload. PREVIEW only — never raises mastery, never
writes canonical truth, never mutates the legacy construction_grading_result."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
_ws = importlib.util.spec_from_file_location(
    "ws_gap1", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py"
)
ws = importlib.util.module_from_spec(_ws)
_ws.loader.exec_module(ws)

_CUR = {"u": "qa_gap1_ws"}
ANS = "工期为 25 个月，合理。"


def _client(tmp: str) -> TestClient:
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame() -> dict:
    cfg = {
        "followup_question_context": {
            "question_id": "M2-2015-30-01",
            "question_type": "case",
            "question": "q",
            "correct_answer": ANS,
        }
    }
    return {"type": "start_turn", "content": ANS, "capability": "deep_question", "language": "zh", "config": cfg}


def _md(c: TestClient) -> dict:
    return ws._receive_result(c, _frame()).get("metadata") or {}


def test_real_ws_grading_conversation_emits_learning_evidence_preview() -> None:
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _md(c)
    assert "construction_grading_result" in md, "no real grading happened on the live path"
    preview = md.get("learning_evidence_preview")
    assert preview is not None, (
        "gap_1 NOT closed: build_learning_evidence_from_context_pack was not called "
        "from the live /api/v1/ws grading runtime"
    )
    # PREVIEW only — authority invariants must hold on the real path.
    assert preview["mastery_raised"] is False
    assert preview["canonical_truth_written"] is False
    # Derived from the unified compiled context, not a re-assembled one.
    assert "compiled_context_provenance" in preview


def test_kill_switch_drops_preview_on_live_path(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED", "1")
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _md(c)
    assert "construction_grading_result" in md
    assert "learning_evidence_preview" not in md


def test_preview_is_append_only_legacy_grading_unchanged(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        on = _md(c)
    monkeypatch.setenv("LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED", "1")
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        off = _md(c)
    assert on.get("construction_grading_result") == off.get("construction_grading_result")
