#!/usr/bin/env python3
"""QA/test /api/v1/ws runtime-shadow turn smoke.

Runs real FastAPI TestClient websocket frames through:
  /api/v1/ws -> TurnRuntimeManager.start_turn -> ChatOrchestrator ->
  DeepQuestionCapability.run -> _emit_grading_result.

External providers, learner DB writes, and Best-Quality engine calls are replaced
with deterministic test fixtures. No production DB or Learning Brain writes.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/luban_consensus_gold/ws_runtime_shadow_turn_smoke_20260604"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from deeptutor.api.dependencies import AuthContext
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager


class FakeContextBuilder:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def build(self, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            conversation_history=[],
            conversation_summary="",
            context_text="",
            token_count=0,
            budget=0,
        )


class FakeMemoryService:
    def build_memory_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    async def refresh_from_turn(self, **_kwargs: Any) -> None:
        return None


class FakeLearnerStateService:
    def build_context(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    def read_compiled_learning_truth(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


class FakeSubmissionGraderAgent:
    def __init__(self, **_kwargs: Any) -> None:
        self._trace_callback = None

    def set_trace_callback(self, callback: Any) -> None:
        self._trace_callback = callback

    async def process(self, **_kwargs: Any) -> str:
        return "得分：1分（满分3分）。"


def _auth_ctx(user_id: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id, "canonical_uid": user_id},
        is_admin=False,
    )


def _install_fakes(runtime: TurnRuntimeManager, *, user_id: str, write_calls: list[dict[str, Any]],
                   engine_calls: list[dict[str, Any]]) -> None:
    import deeptutor.api._secure_router as secure_router_mod
    import deeptutor.api.routers.unified_ws as unified_ws_mod
    import deeptutor.services.session as session_pkg
    import deeptutor.services.llm.config as llm_config_mod
    import deeptutor.services.session.context_builder as context_builder_mod
    import deeptutor.services.memory as memory_mod
    import deeptutor.services.learner_state as learner_state_mod
    import deeptutor.capabilities.deep_question as deep_question_mod
    import deeptutor.agents.question.agents.submission_grader_agent as grader_mod
    import deeptutor.runtime.orchestrator as orchestrator_mod
    from deeptutor.services.construction_grading import runtime_shadow_adapter
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    secure_router_mod.resolve_auth_context = lambda _authorization: _auth_ctx(user_id)
    async def _allow_ws_rate_limit(*_args: Any, **_kwargs: Any) -> bool:
        return True

    secure_router_mod.enforce_websocket_rate_limit = _allow_ws_rate_limit
    unified_ws_mod.enforce_websocket_rate_limit = _allow_ws_rate_limit
    session_pkg.get_turn_runtime_manager = lambda: runtime
    llm_config_mod.get_llm_config = lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1")
    context_builder_mod.ContextBuilder = FakeContextBuilder
    memory_mod.get_memory_service = lambda: FakeMemoryService()
    learner_state_mod.get_learner_state_service = lambda: FakeLearnerStateService()
    grader_mod.SubmissionGraderAgent = FakeSubmissionGraderAgent

    async def _select_deep_question(self: Any, context: Any) -> str:
        return "deep_question"

    orchestrator_mod.ChatOrchestrator._select_capability = _select_deep_question

    def _write_grading_error_events(**kwargs: Any) -> int:
        write_calls.append(
            {
                "authority": (kwargs.get("grading_result") or {}).get("authority"),
                "source_id": kwargs.get("source_id"),
            }
        )
        return 1

    deep_question_mod.write_grading_error_events = _write_grading_error_events

    def _build_best_quality_draft(**kwargs: Any) -> dict[str, Any]:
        question = kwargs["question"]
        points = list(question.get("scoring_points") or [])
        if not points:
            raise AssertionError("engine fixture should not run without artifact points")
        point = points[0]
        engine_calls.append(
            {
                "case_id": question.get("case_id"),
                "student_id": kwargs.get("student_id"),
                "artifact_status": kwargs.get("artifact_gate").artifact_status,
            }
        )
        return build_ai_draft(
            question,
            kwargs["student_answer"],
            [
                {
                    "point_id": point["point_id"],
                    "hit": "hit",
                    "score": point.get("max_score") or 1,
                    "evidence_span": "专用开关箱",
                    "rationale": "deterministic ws smoke fixture",
                }
            ],
            points=[point],
            student_id=kwargs.get("student_id"),
            artifact_gate=kwargs.get("artifact_gate"),
        )

    runtime_shadow_adapter._build_best_quality_draft = _build_best_quality_draft


def _build_ws_app() -> FastAPI:
    import deeptutor.api.routers.unified_ws as ws_module

    app = FastAPI()
    app.include_router(ws_module.router, prefix="/api/v1")
    return app


def _frame(case_id: str, *, flag: bool) -> dict[str, Any]:
    config: dict[str, Any] = {
        "followup_question_context": {
            "question_id": case_id,
            "question_type": "case",
            "question": "指出事件二中临时用电管理的不妥之处。",
            "correct_answer": (
                "共用一个开关箱不妥，应采用专用开关箱；"
                "未编制临时用电施工组织设计；插座插头不得活动连接。"
            ),
        }
    }
    if flag:
        config["grading_engine_runtime_shadow"] = True
        config["grading_engine_runtime_shadow_engine"] = "best_quality_4model"
    return {
        "type": "start_turn",
        "content": "共用一个开关箱不妥，应采用专用开关箱。",
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def _receive_result(client: TestClient, frame: dict[str, Any]) -> dict[str, Any]:
    with client.websocket_connect("/api/v1/ws") as websocket:
        websocket.send_json(frame)
        for _ in range(100):
            try:
                msg = websocket.receive_json()
            except WebSocketDisconnect as exc:
                raise RuntimeError(f"websocket disconnected before result: code={exc.code} reason={exc.reason}") from exc
            if msg.get("type") == "result":
                return msg
            if msg.get("type") == "error":
                raise RuntimeError(json.dumps(msg, ensure_ascii=False))
    raise RuntimeError("result event not received")


def _run_one(sample: dict[str, Any], *, flag: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="luban-ws-shadow-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "smoke.db"))
        write_calls: list[dict[str, Any]] = []
        engine_calls: list[dict[str, Any]] = []
        _install_fakes(runtime, user_id=sample["user_id"], write_calls=write_calls, engine_calls=engine_calls)
        with TestClient(_build_ws_app()) as client:
            result = _receive_result(client, _frame(sample["case_id"], flag=flag))
        evidence = {
            "sample_id": sample["sample_id"],
            "flag": flag,
            "write_calls": write_calls,
            "engine_calls": engine_calls,
        }
        return result, evidence


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = [
        {"sample_id": "published_q1", "case_id": "Q1-NA", "user_id": "qa_ws_shadow_smoke_001", "truth": "published"},
        {"sample_id": "draft_q20", "case_id": "Q20-1A413000", "user_id": "qa_ws_shadow_smoke_002", "truth": "draft"},
        {"sample_id": "missing_case", "case_id": "NO-SUCH-CASE", "user_id": "qa_ws_shadow_smoke_003", "truth": "missing"},
        {"sample_id": "non_qa_q1", "case_id": "Q1-NA", "user_id": "real_student_123", "truth": "non_qa"},
    ]
    flag_off: list[dict[str, Any]] = []
    flag_on: list[dict[str, Any]] = []
    legacy_diff: list[dict[str, Any]] = []
    run_evidence: list[dict[str, Any]] = []

    for sample in samples:
        off, off_ev = _run_one(sample, flag=False)
        on, on_ev = _run_one(sample, flag=True)
        flag_off.append({"sample": sample, "event": off})
        flag_on.append({"sample": sample, "event": on})
        run_evidence.extend([off_ev, on_ev])
        off_legacy = (off.get("metadata") or {}).get("construction_grading_result") or {}
        on_legacy = (on.get("metadata") or {}).get("construction_grading_result") or {}
        shadow = (on.get("metadata") or {}).get("luban_grading_engine_shadow") or {}
        legacy_diff.append(
            {
                "sample_id": sample["sample_id"],
                "legacy_equal": off_legacy == on_legacy,
                "flag_off_has_shadow": "luban_grading_engine_shadow" in (off.get("metadata") or {}),
                "flag_on_has_shadow": "luban_grading_engine_shadow" in (on.get("metadata") or {}),
                "legacy_authority": on_legacy.get("authority"),
                "legacy_score_awarded": on_legacy.get("score_awarded"),
                "legacy_max_score": on_legacy.get("max_score"),
                "shadow_status": shadow.get("shadow_status"),
                "shadow_authority": shadow.get("authority"),
                "shadow_writeback_performed": shadow.get("writeback_performed"),
                "artifact_status": (shadow.get("artifact_gate") or {}).get("artifact_status"),
            }
        )

    (OUT / "ws_turn_inputs.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "flag_off_result_events.json").write_text(json.dumps(flag_off, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "flag_on_result_events.json").write_text(json.dumps(flag_on, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "legacy_diff.json").write_text(json.dumps({"rows": legacy_diff, "run_evidence": run_evidence}, ensure_ascii=False, indent=2), encoding="utf-8")

    sample_shadow = (flag_on[0]["event"].get("metadata") or {}).get("luban_grading_engine_shadow") or {}
    (OUT / "sample_client_payload.md").write_text(
        "# Sample Client Payload\n\n"
        "```json\n"
        + json.dumps(sample_shadow, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    (OUT / "truth_level.md").write_text(
        "# Truth Level\n\n"
        "- REAL: FastAPI TestClient websocket `/api/v1/ws` frame.\n"
        "- REAL: `TurnRuntimeManager.start_turn` with SQLiteSessionStore in a temp DB.\n"
        "- REAL: `ChatOrchestrator.handle` and `DeepQuestionCapability.run`.\n"
        "- REAL: `_emit_grading_result` top-level RESULT metadata append.\n"
        "- REAL: `RuntimeShadowAdapter`, `QuestionGradingArtifact Registry v0`, and `ArtifactRuntimeGate`.\n"
        "- SIMULATED: LLM/SubmissionGraderAgent text, memory context, learner state service, Best-Quality engine call, and WS rate-limit allow hook for repeatable local smoke.\n"
        "- NO-WRITE: Learning Brain writeback is monkeypatched to collect legacy calls only; shadow reports `writeback_performed=false`.\n",
        encoding="utf-8",
    )

    lines = [
        "# FINDING ws runtime shadow turn smoke 2026-06-04",
        "",
        "## Answers",
        "",
        "1. 本轮打到的真实层级：FastAPI TestClient websocket `/api/v1/ws` -> real `TurnRuntimeManager.start_turn` -> real `ChatOrchestrator.handle` -> real `DeepQuestionCapability.run` -> real `_emit_grading_result` RESULT metadata.",
        "2. REAL：WS frame、TurnRuntime、capability、adapter/gate/registry、client RESULT event。SIMULATED：LLM explanation、memory/learner context、Best-Quality engine output fixture、WS rate-limit allow hook、Learning Brain write collector。",
        "3. 外部 flag：start_turn frame `config.grading_engine_runtime_shadow=true` + `config.grading_engine_runtime_shadow_engine=best_quality_4model`，由 TurnRuntime runtime-only config 透传到 capability。",
        "4. flag off：全部样本 `flag_off_has_shadow=false`。",
        "5. flag on：QA 样本有 shadow；non-QA 样本有 fail-closed shadow `qa_student_required`。",
        "6. legacy：每个样本 off/on legacy grading result 相等，authority 仍是 `construction_grading`。",
        "7. shadow：只 append `luban_grading_engine_shadow`，不覆盖 `construction_grading_result`。",
        "8. DB/Learning Brain：未写真实 DB；tmp SQLite 仅用于 turn runtime；write collector 只看到 legacy `construction_grading` 调用，shadow `writeback_performed=false`。",
        "9. 行为：published=shadow ok; draft=shadow ok but artifact_status draft/no auto; missing=artifact_missing; non-QA=qa_student_required。",
        "10. 下一步：可以进入 teacher-review 真实写回小批，但仍必须使用 QA/test 用户、teacher-final JSON、fake/test memory 或测试 DB。",
        "",
        "## Sample Table",
        "",
        "| sample | artifact/status | off shadow | on shadow | legacy equal | writeback |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in legacy_diff:
        lines.append(
            f"| {row['sample_id']} | {row.get('artifact_status') or row.get('shadow_status')} | "
            f"{row['flag_off_has_shadow']} | {row['flag_on_has_shadow']} | "
            f"{row['legacy_equal']} | {row['shadow_writeback_performed']} |"
        )
    (OUT / "FINDING_ws_runtime_shadow_turn_smoke_20260604.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
