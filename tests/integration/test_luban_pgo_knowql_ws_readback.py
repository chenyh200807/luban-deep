"""G2 integration: PGO KnowQL readback over the real ``/api/v1/ws`` path.

The drill drives FastAPI TestClient -> /api/v1/ws -> TurnRuntimeManager ->
DeepQuestionCapability -> PGO shadow attachment. It proves the client-visible
result event can read back the KnowQL query evidence without making the PGO
shadow a production grade or learner-truth writer.
"""
from __future__ import annotations

import importlib.util
import signal
import tempfile
from pathlib import Path
from typing import Any

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient

from deeptutor.services.learner_state.next_best_action import build_next_best_actions
from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)
from deeptutor.services.learner_state.service import LearnerStateService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "ws_smoke_pgo_knowql",
    REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py",
)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

_CUR = {"user": "qa_pgo_knowql_ws"}
_KNOWN_PGO_QID = "2015::EXAM_XW2015_CASE_1::E0"
_ANSWER = "施工总进度计划表，开竣工日期及工期一览表。"


class _WsReceiveTimeout(TimeoutError):
    pass


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root

    def get_tutor_state_root(self) -> Path:
        return self._root / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self) -> Path:
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MemberServiceStub:
    def get_profile(self, user_id: str) -> dict[str, str]:
        return {"user_id": user_id}


def _client():
    tmp = tempfile.mkdtemp(prefix="luban-pgo-knowql-ws-")
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "pgo_knowql.db"))
    ws._install_fakes(runtime, user_id=_CUR["user"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
    return TestClient(ws._build_ws_app())


def _frame(question_id: str, *, flag: bool = True) -> dict[str, Any]:
    config: dict[str, Any] = {
        "followup_question_context": {
            "question_id": question_id,
            "question_type": "case",
            "question": "施工总进度计划还缺少哪些内容？",
            "correct_answer": _ANSWER,
        }
    }
    if flag:
        config["grading_engine_pgo_shadow"] = True
    return {
        "type": "start_turn",
        "content": _ANSWER,
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def _receive_result_with_timeout(
    client: TestClient,
    frame: dict[str, Any],
    *,
    seconds: int = 45,
) -> dict[str, Any]:
    def _raise_timeout(_signum, _frame_obj) -> None:
        raise _WsReceiveTimeout(f"PGO KnowQL WS readback did not finish within {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return ws._receive_result(client, frame)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def _metadata(question_id: str, *, user: str = "qa_pgo_knowql_ws") -> dict[str, Any]:
    _CUR["user"] = user
    with _client() as client:
        result = _receive_result_with_timeout(client, _frame(question_id))
    return result.get("metadata") or {}


def test_ws_pgo_shadow_readback_consumes_real_hash_pinned_knowql_query(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")

    metadata = _metadata(_KNOWN_PGO_QID)

    shadow = metadata.get("luban_case_rubric_pgo_shadow")
    assert shadow is not None
    assert shadow["authority"] == "luban_case_rubric_pgo_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False
    assert shadow["shadow_status"] == "ok"
    assert shadow["point_verdicts"]
    assert shadow["score"]["max_score"] > 0
    query = shadow["knowql_query"]
    assert query["executor"] == "retrieve_rubric"
    assert query["runtime_consumed"] is True
    assert query["found"] is True
    assert query["question_id"] == _KNOWN_PGO_QID
    assert query["artifact_version"] == "case_rubric_scored_pgo"
    assert query["scoring_point_count"] > 0
    shadow_blob = str(shadow)
    assert "official_slice" not in shadow_blob
    assert "knowledge_point" not in str(shadow.get("runtime_points", []))
    assert "answer_key_authority" not in shadow_blob


def test_ws_pgo_shadow_readback_exposes_knowql_fail_open_without_touching_legacy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")

    metadata = _metadata("missing-pgo-qid")

    assert "construction_grading_result" in metadata
    shadow = metadata.get("luban_case_rubric_pgo_shadow")
    assert shadow is not None
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False
    query = shadow["knowql_query"]
    assert query["runtime_consumed"] is True
    assert query["found"] is False
    assert query["fail_open"] is True
    assert query["reason"] == "artifact_missing"


def test_ws_pgo_shadow_readback_blocks_non_qa_user(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")

    metadata = _metadata(_KNOWN_PGO_QID, user="real_student_777")

    assert "construction_grading_result" in metadata
    assert "luban_case_rubric_pgo_shadow" not in metadata


def test_ws_pgo_same_attempt_grading_to_brain_readback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    user_id = "qa_pgo_knowql_ws_g3"
    _CUR["user"] = user_id

    service = LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_MemberServiceStub(),
    )
    import deeptutor.services.learner_state as learner_state_mod
    import deeptutor.capabilities.deep_question as deep_question_mod

    original_build = deep_question_mod.DeepQuestionCapability._build_submission_context

    def _build_submission_context_with_pgo(
        question_context: dict[str, Any],
        user_answer: str,
        *,
        raw_submission: str = "",
    ) -> dict[str, Any]:
        graded = original_build(
            question_context,
            user_answer,
            raw_submission=raw_submission,
        )
        graded["pgo_grading_contract"] = {
            "question_id": _KNOWN_PGO_QID,
            "official_total_score": 10,
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "scoring_points": [
                {
                    "point_id": "P1",
                    "official_slice": "施工总进度计划表",
                    "authority_source": "official_answer_verbatim",
                    "span_hash": "sha256:P1",
                    "sub_type": "free_text_point",
                },
                {
                    "point_id": "P2",
                    "official_slice": "开竣工日期及工期一览表",
                    "authority_source": "official_answer_verbatim",
                    "span_hash": "sha256:P2",
                    "sub_type": "free_text_point",
                },
            ],
        }
        graded["pgo_point_verdicts"] = {"P1": "hit", "P2": "miss"}
        return graded

    monkeypatch.setattr(learner_state_mod, "get_learner_state_service", lambda: service)
    monkeypatch.setattr(
        deep_question_mod.DeepQuestionCapability,
        "_build_submission_context",
        staticmethod(_build_submission_context_with_pgo),
    )

    tmp = tempfile.mkdtemp(prefix="luban-pgo-knowql-ws-g3-")
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "pgo_g3.db"))
    ws._install_fakes(runtime, user_id=user_id, write_calls=[], engine_calls=[])
    monkeypatch.setattr(learner_state_mod, "get_learner_state_service", lambda: service)
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(user_id)

    with TestClient(ws._build_ws_app()) as client:
        result = _receive_result_with_timeout(client, _frame(_KNOWN_PGO_QID))

    metadata = result.get("metadata") or {}
    shadow = metadata.get("luban_case_rubric_pgo_shadow") or {}
    assert shadow["shadow_status"] == "ok"
    assert shadow["writeback_performed"] is False
    g3 = metadata.get("pgo_grading_to_brain") or {}
    assert g3["writeback_count"] == 1
    assert g3["artifact_version"] == "case_rubric_scored_pgo"
    assert g3["canonical_truth_written"] is False
    assert g3["claim_promotion_allowed"] is False
    assert g3["scoring_point_map_readback"]["items_count"] == 1
    assert g3["next_best_action"]["prescription_authority"] == "training_intent"

    events = service.list_memory_events(user_id)
    pgo_events = [
        event for event in events
        if (event.payload_json or {}).get("learning_signal_type") == "pgo_case_rubric_shadow"
    ]
    assert len(pgo_events) == 1
    payload = pgo_events[0].payload_json
    assert payload["canonical_truth_written"] is False
    assert payload["claim_promotion_allowed"] is False
    assert payload["rubric"]["artifact_version"] == "case_rubric_scored_pgo"
    assert "施工总进度计划表" not in str(payload)
    assert "开竣工日期及工期一览表" not in str(payload)

    point_map = build_scoring_point_map_read_projection(events=events, user_id=user_id)
    missed = [item for item in point_map["items"] if item["point_id"] == "P2"]
    assert missed
    assert missed[0]["evidence_refs"] == [pgo_events[0].event_id]
    actions = build_next_best_actions(
        user_id=user_id,
        training_intents=[missed[0]["next_action"]["intent"]],
    )
    assert actions[0]["prescription_authority"] == "training_intent"
    assert not (tmp_path / "learner_state" / user_id / "COMPILED_TRUTH.json").exists()
