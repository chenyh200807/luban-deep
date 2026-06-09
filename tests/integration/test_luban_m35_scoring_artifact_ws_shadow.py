"""M35 integration: scoring artifact shadow over the real ``/api/v1/ws`` path.

The drill drives the production websocket route through TurnRuntimeManager and
DeepQuestionCapability. The M35 lane is append-only metadata: legacy case grading
must remain intact, and no DB / learner truth write is allowed.
"""
from __future__ import annotations

import importlib.util
import signal
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.api.routers.unified_ws import _bind_authenticated_user
from deeptutor.capabilities.deep_question import _m35_authenticated_user_id_from_context
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

_spec = importlib.util.spec_from_file_location(
    "ws_smoke_m35",
    REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py",
)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

_CUR = {"user": "qa_m35_ws"}
_QID = "Q1-NA"
_ANSWER = "施工总进度计划表，开竣工日期及工期一览表，资源需要量及供应平衡表。"


class _WsReceiveTimeout(TimeoutError):
    pass


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mkdtemp(prefix="luban-m35-ws-")
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m35.db"))
    ws._install_fakes(runtime, user_id=_CUR["user"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
    with TestClient(ws._build_ws_app()) as c:
        yield c


def _frame(flag: bool, *, config_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "followup_question_context": {
            "question_id": _QID,
            "question_type": "case",
            "question": "施工总进度计划还缺少哪些内容？",
            "correct_answer": _ANSWER,
        }
    }
    if flag:
        cfg["grading_engine_m35_artifact_shadow"] = True
    if config_extra:
        cfg.update(config_extra)
    return {
        "type": "start_turn",
        "content": _ANSWER,
        "capability": "deep_question",
        "language": "zh",
        "config": cfg,
    }


def _receive_result_with_timeout(
    client: TestClient,
    frame: dict[str, Any],
    *,
    seconds: int = 20,
) -> dict[str, Any]:
    def _raise_timeout(_signum, _frame_obj) -> None:
        raise _WsReceiveTimeout(f"M35 WS smoke did not finish within {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return ws._receive_result(client, frame)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def _meta(
    client: TestClient,
    flag: bool,
    *,
    user: str = "qa_m35_ws",
) -> dict[str, Any]:
    _CUR["user"] = user
    return (_receive_result_with_timeout(client, _frame(flag)).get("metadata") or {})


def test_ws_flag_off_is_legacy_only(client: TestClient) -> None:
    metadata = _meta(client, flag=False)
    assert "construction_grading_result" in metadata
    assert "luban_m35_scoring_artifact_shadow" not in metadata


def test_ws_flag_on_appends_m35_artifact_shadow(client: TestClient) -> None:
    metadata = _meta(client, flag=True)
    shadow = metadata.get("luban_m35_scoring_artifact_shadow")
    assert shadow is not None
    assert shadow["authority"] == "grading_engine_m35_artifact_shadow"
    assert shadow["official_score_allowed"] is False
    assert shadow["quality_claim_allowed"] is False
    assert shadow["evaluation_tier"] == "shape_stub"
    assert shadow["verdict_ceiling"] == "NO-GO_OR_SHAPE_ONLY"
    assert shadow["production_write_count"] == 0
    assert shadow["canonical_truth_written"] is False
    assert shadow["db_write_count"] == 0
    assert shadow["remote_write_count"] == 0
    assert shadow["rag_lookup_count"] == 0
    assert shadow["artifact_version"]
    assert shadow["legacy_artifact_status"] in {"published", "draft", "blocked"}
    assert shadow["m35_runtime_status"] in {"release_candidate", "shadow_candidate", "blocked"}
    assert isinstance(shadow["point_matches"], list)
    assert shadow["point_matches"]


def test_ws_legacy_result_never_changes_when_shadow_enabled(client: TestClient) -> None:
    off = _meta(client, flag=False).get("construction_grading_result")
    on = _meta(client, flag=True).get("construction_grading_result")
    assert off == on


def test_ws_m35_env_kill_switch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_M35_ARTIFACT_SHADOW_ENABLED", "false")
    metadata = _meta(client, flag=True)
    assert "luban_m35_scoring_artifact_shadow" not in metadata
    assert "construction_grading_result" in metadata


def test_ws_non_qa_user_blocked_without_explicit_authorization(client: TestClient) -> None:
    metadata = _meta(client, flag=True, user="real_student_777")
    assert "luban_m35_scoring_artifact_shadow" not in metadata
    assert "construction_grading_result" in metadata


def test_ws_env_cannot_expand_shadow_to_real_student(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUBAN_M35_ARTIFACT_SHADOW_COHORT", "real_")
    metadata = _meta(client, flag=True, user="real_student_777")
    assert "luban_m35_scoring_artifact_shadow" not in metadata
    assert "construction_grading_result" in metadata


def test_ws_adapter_rejects_forged_billing_context_user_id() -> None:
    payload = _frame(
        True,
        config_extra={
            "billing_context": {
                "source": "authenticated_ws",
                "user_id": "operator_m35_ws",
            }
        },
    )
    with pytest.raises(PermissionError):
        _bind_authenticated_user(payload, ws._auth_ctx("real_student_777"))


def test_m35_identity_reader_does_not_trust_billing_or_request_config() -> None:
    context = SimpleNamespace(
        metadata={"billing_context": {"user_id": "operator_m35_ws"}},
        config_overrides={"user_id": "operator_m35_ws"},
    )

    assert _m35_authenticated_user_id_from_context(context) == ""


def test_ws_operator_cohort_can_receive_shadow(client: TestClient) -> None:
    metadata = _meta(client, flag=True, user="operator_m35_ws")
    shadow = metadata.get("luban_m35_scoring_artifact_shadow")
    assert shadow is not None
    assert shadow["production_write_count"] == 0
    assert shadow["canonical_truth_written"] is False


def test_ws_shadow_builder_failure_fails_closed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeptutor.services.construction_grading.m35_artifact_shadow as shadow_mod

    def _boom(**_kwargs):
        raise RuntimeError("shadow builder unavailable")

    monkeypatch.setattr(shadow_mod, "build_m35_artifact_shadow_payload", _boom)
    metadata = _meta(client, flag=True, user="qa_m35_ws")
    shadow = metadata.get("luban_m35_scoring_artifact_shadow")
    assert shadow is not None
    assert shadow["shadow_status"] == "artifact_shadow_unavailable"
    assert shadow["evaluation_tier"] == "shape_stub"
    assert shadow["quality_claim_allowed"] is False
    assert shadow["verdict_ceiling"] == "NO-GO_OR_SHAPE_ONLY"
    assert shadow["official_score_allowed"] is False
    assert shadow["production_write_count"] == 0
    assert shadow["canonical_truth_written"] is False
    assert shadow["db_write_count"] == 0
    assert shadow["remote_write_count"] == 0
    assert shadow["rag_lookup_count"] == 0
    assert shadow["point_matches"] == []
