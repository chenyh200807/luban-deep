#!/usr/bin/env python3
"""真实 /api/v1/ws 全链路 V1 演示 —— 看 V1 在真实 WebSocket 回合里学生最终读到的话术。

打的是真实链路：
  /api/v1/ws -> TurnRuntimeManager.start_turn -> ChatOrchestrator -> DeepQuestionCapability.run
  -> _emit_grading_result -> _grade_case_rubric_v1(真实 DeepSeek) -> render_case_rubric_feedback

只模拟与本演示无关的外围（context builder / memory / learner state / 限流 / Learning Brain 写）。
V1 判分用真实 DeepSeek（读 .env 的 DEEPSEEK_API_KEY），不写库、不写 learner truth，official_score_allowed=False。

用法：
  python scripts/run_luban_v1_ws_live_demo.py            # 默认在库题 + 默认作答
  python scripts/run_luban_v1_ws_live_demo.py --qid <在库QID> --answer "<学生作答>"
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_deepseek_key() -> str:
    import os
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text("utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["DEEPSEEK_API_KEY"] = key
                return key
    raise SystemExit("DEEPSEEK_API_KEY 未配置")


_DEFAULT_QID = "EXAM_1A413030_P0012_04::E3"
_DEFAULT_STEM = "某工程现浇混凝土施工，列出该工程可选用的混凝土水平运输设备、垂直运输设备和泵送设备。"
_DEFAULT_ANSWER = "水平运输用手推车和机动翻斗车；垂直运输用塔吊；混凝土泵送用汽车泵和布料机。"


class _FakeContextBuilder:
    def __init__(self, *_a: Any, **_k: Any) -> None: ...
    async def build(self, **_k: Any) -> SimpleNamespace:
        return SimpleNamespace(conversation_history=[], conversation_summary="",
                               context_text="", token_count=0, budget=0)


class _FakeMemory:
    def build_memory_context(self, *_a: Any, **_k: Any) -> str: return ""
    async def refresh_from_turn(self, **_k: Any) -> None: return None


class _FakeLearnerState:
    def build_context(self, *_a: Any, **_k: Any) -> str: return ""
    def read_compiled_learning_truth(self, *_a: Any, **_k: Any) -> dict[str, Any]: return {}


def _auth_ctx(user_id: str):
    from deeptutor.api.dependencies import AuthContext
    return AuthContext(user_id=user_id, provider="test", token="t",
                       claims={"uid": user_id, "canonical_uid": user_id}, is_admin=False)


def _install_fakes(runtime: Any, *, user_id: str) -> None:
    import deeptutor.api._secure_router as secure_router_mod
    import deeptutor.api.routers.unified_ws as unified_ws_mod
    import deeptutor.services.session as session_pkg
    import deeptutor.services.session.context_builder as context_builder_mod
    import deeptutor.services.memory as memory_mod
    import deeptutor.services.learner_state as learner_state_mod
    import deeptutor.capabilities.deep_question as deep_question_mod
    import deeptutor.runtime.orchestrator as orchestrator_mod

    secure_router_mod.resolve_auth_context = lambda _a: _auth_ctx(user_id)

    async def _allow(*_a: Any, **_k: Any) -> bool: return True
    secure_router_mod.enforce_websocket_rate_limit = _allow
    unified_ws_mod.enforce_websocket_rate_limit = _allow
    session_pkg.get_turn_runtime_manager = lambda: runtime
    context_builder_mod.ContextBuilder = _FakeContextBuilder
    memory_mod.get_memory_service = lambda: _FakeMemory()
    learner_state_mod.get_learner_state_service = lambda: _FakeLearnerState()

    async def _select_dq(self: Any, context: Any) -> str: return "deep_question"
    orchestrator_mod.ChatOrchestrator._select_capability = _select_dq

    def _write(**kwargs: Any) -> int: return 1  # no Learning Brain write
    deep_question_mod.write_grading_error_events = _write


def _frame(qid: str, stem: str, answer: str) -> dict[str, Any]:
    return {
        "type": "start_turn",
        "content": answer,
        "capability": "deep_question",
        "language": "zh",
        "config": {
            "followup_question_context": {
                "question_id": qid,
                "question_type": "case",
                "question": stem,
                "correct_answer": stem,  # V0 旁路用；V1 用编译 rubric（真实参考答案）
            },
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qid", default=_DEFAULT_QID)
    ap.add_argument("--stem", default=_DEFAULT_STEM)
    ap.add_argument("--answer", default=_DEFAULT_ANSWER)
    ap.add_argument("--user", default="qa_v1_live")
    args = ap.parse_args()

    import os
    _load_deepseek_key()
    os.environ["LUBAN_CASE_RUBRIC_V1_ENABLED"] = "true"  # 全局开 V1（仍受 cohort 门控）

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    import deeptutor.api.routers.unified_ws as ws_module
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.session.turn_runtime import TurnRuntimeManager

    with tempfile.TemporaryDirectory(prefix="luban-v1-ws-") as tmp:
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "demo.db"))
        _install_fakes(runtime, user_id=args.user)
        app = FastAPI()
        app.include_router(ws_module.router, prefix="/api/v1")

        chunks: list[str] = []
        result: dict[str, Any] | None = None
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json(_frame(args.qid, args.stem, args.answer))
                for _ in range(400):
                    try:
                        msg = ws.receive_json()
                    except WebSocketDisconnect as exc:
                        raise RuntimeError(f"ws disconnected: {exc.code} {exc.reason}") from exc
                    t = msg.get("type")
                    if t in ("content", "chunk") and msg.get("content"):
                        chunks.append(str(msg["content"]))
                    elif t == "result":
                        result = msg
                        break
                    elif t == "error":
                        raise RuntimeError(json.dumps(msg, ensure_ascii=False))
        if result is None:
            raise RuntimeError("未收到 result 事件")

    meta = result.get("metadata") or {}
    bar = "=" * 72
    print(bar)
    print("真实链路：/api/v1/ws -> TurnRuntime -> Orchestrator -> DeepQuestion -> _emit_grading_result")
    print("用户(cohort):", args.user, "| 题:", args.qid)
    print("学生作答:", args.answer)
    print(bar)
    print("\n########## 学生在聊天里读到的最终 response（result.response）##########\n")
    print(str(result.get("response") or meta.get("response") or "(空)"))
    print("\n########## 流式 content 拼接（学生看到的流式过程）##########\n")
    print("".join(chunks) or "(无流式 chunk)")
    v1 = meta.get("luban_case_rubric_v1") or {}
    print("\n########## 结构化 V1 payload（喂 Grading-to-Brain）##########\n")
    print("status:", v1.get("status"), "| official_score_allowed:", v1.get("official_score_allowed"))
    ev = v1.get("grading_event") or {}
    if ev:
        print("得分:", ev.get("awarded_score"), "/", ev.get("max_score"),
              "| high_risk_review:", ev.get("high_risk_review"))
    le = v1.get("learning_evidence") or {}
    if le:
        print("weak_points:", [w.get("concept_label") for w in le.get("weak_points") or []],
              "| writeback_performed:", le.get("writeback_performed"))
    print("\nlegacy construction_grading_result.authority:",
          (meta.get("construction_grading_result") or {}).get("authority"))
    print(bar)


if __name__ == "__main__":
    main()
