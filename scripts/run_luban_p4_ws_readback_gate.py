#!/usr/bin/env python3
"""P4 local real-/api/v1/ws readback gate for grading-to-brain.

This gate drives the actual FastAPI WebSocket route (`/api/v1/ws`) with a
deterministic local DeepQuestion runtime. The runtime uses the existing
DeepQuestionCapability result path and its existing grading writeback seam, but
patches `get_learner_state_service()` to an isolated local LearnerStateService
under the artifact directory.

No dev server is started. No provider, production DB, canonical truth,
published registry, remote host, or Aliyun state is touched.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.api.dependencies import AuthContext  # noqa: E402
from deeptutor.capabilities.deep_question import DeepQuestionCapability  # noqa: E402
from deeptutor.core.context import UnifiedContext  # noqa: E402
from deeptutor.core.stream import StreamEvent, StreamEventType  # noqa: E402
from deeptutor.core.stream_bus import StreamBus  # noqa: E402
from scripts.run_luban_p2_live_readback_gate import _local_service  # noqa: E402
from scripts.run_luban_p3_api_readback_gate import (  # noqa: E402
    _LocalMemberService,
    _LocalMistakeBookService,
    _LocalNotebookCardService,
    _build_app as _build_mobile_app,
    _output_projection_hash,
    _patched_mobile_module,
    _report_projection_hash,
    _sha,
)

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/p4_ws_readback_20260612"
USER_ID = "qa_p4_ws_readback"
BOT_ID = "construction-exam"
_FAKE_MODULE_NAMES = (
    "deeptutor.agents.question.coordinator",
    "deeptutor.agents.question.agents.submission_grader_agent",
    "deeptutor.services.llm.config",
)


class _NoWriteLearnerStateService:
    def append_memory_event(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("learner state writeback disabled for negative gate")


def _auth_ctx(user_id: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="p4-local",
        token="p4-local-token",
        claims={"uid": user_id, "canonical_uid": user_id},
        is_admin=False,
    )


def _artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _install_module(fullname: str, **attrs: Any) -> types.ModuleType:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            sys.modules[pkg_name] = pkg
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[fullname] = module
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        setattr(parent, parts[-1], module)
    return module


def _module_restore_names(module_names: tuple[str, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    for fullname in module_names:
        parts = fullname.split(".")
        for depth in range(2, len(parts) + 1):
            names.add(".".join(parts[:depth]))
    return tuple(sorted(names, key=lambda name: name.count("."), reverse=True))


def _snapshot_modules(module_names: tuple[str, ...]) -> dict[str, tuple[types.ModuleType | None, Any]]:
    snapshot: dict[str, tuple[types.ModuleType | None, Any]] = {}
    for fullname in _module_restore_names(module_names):
        parts = fullname.split(".")
        parent_name = ".".join(parts[:-1])
        attr_name = parts[-1]
        parent = sys.modules.get(parent_name)
        parent_attr = getattr(parent, attr_name, None) if parent is not None else None
        snapshot[fullname] = (sys.modules.get(fullname), parent_attr)
    return snapshot


def _restore_modules(snapshot: dict[str, tuple[types.ModuleType | None, Any]]) -> None:
    for fullname, (old_module, old_parent_attr) in sorted(
        snapshot.items(),
        key=lambda item: item[0].count("."),
        reverse=True,
    ):
        parts = fullname.split(".")
        parent = sys.modules.get(".".join(parts[:-1]))
        attr_name = parts[-1]
        if old_module is None:
            sys.modules.pop(fullname, None)
        else:
            sys.modules[fullname] = old_module
        if parent is None:
            continue
        if old_parent_attr is None:
            try:
                delattr(parent, attr_name)
            except AttributeError:
                pass
        else:
            setattr(parent, attr_name, old_parent_attr)


def _install_deep_question_fakes() -> dict[str, tuple[types.ModuleType | None, Any]]:
    snapshot = _snapshot_modules(_FAKE_MODULE_NAMES)

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for P4 grading gate")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback: Any) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "得分：1分（满分3分）。"

    _install_module("deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoordinator)
    _install_module(
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="local", base_url="local", api_version="v1"),
    )
    return snapshot


async def _collect_events(run_coro: Any) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await run_coro(bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


class _DeepQuestionRuntime:
    def __init__(self) -> None:
        self.started_payload: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        self.started_payload = dict(payload)
        config = dict(payload.get("config") or {})
        billing_context = config.get("billing_context") if isinstance(config.get("billing_context"), dict) else {}
        user_id = str(billing_context.get("user_id") or USER_ID).strip()
        followup = config.get("followup_question_context") if isinstance(config.get("followup_question_context"), dict) else {}
        raw_answer = str(payload.get("content") or "").strip()
        context = UnifiedContext(
            session_id=str(payload.get("session_id") or "session_p4_ws_readback"),
            user_message=f"[History Context]\n用户刚做完题。\n\n[User Question]\n{raw_answer}",
            language=str(payload.get("language") or "zh"),
            config_overrides={**config, "bot_id": BOT_ID},
            metadata={
                "user_id": user_id,
                "billing_context": dict(billing_context),
                "bot_id": BOT_ID,
                "raw_user_message": raw_answer,
                "conversation_context_text": "用户刚做完一道建筑实务案例题。",
                "turn_semantic_decision": {"next_action": "route_to_grading"},
                "question_followup_action": {
                    "intent": "answer_questions",
                    "answers": [{"question_id": followup.get("question_id"), "answer": raw_answer}],
                },
                "question_followup_context": dict(followup),
            },
        )
        events = await _collect_events(lambda bus: DeepQuestionCapability().run(context, bus))
        self.events = [event.to_dict() for event in events]
        for idx, event in enumerate(self.events, start=1):
            event["session_id"] = context.session_id
            event["turn_id"] = "turn_p4_ws_readback"
            event["seq"] = idx
        return {"id": context.session_id}, {"id": "turn_p4_ws_readback", "capability": "deep_question"}

    async def subscribe_turn(self, _turn_id: str, after_seq: int = 0) -> Iterator[dict[str, Any]]:
        for event in self.events:
            if int(event.get("seq") or 0) > after_seq:
                yield event


def _build_ws_app(router: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@contextmanager
def _patched_ws_runtime(
    *,
    learner_state_service: Any,
    enable_ws_learner_state_writeback: bool,
) -> Iterator[_DeepQuestionRuntime]:
    fake_module_snapshot = _install_deep_question_fakes()
    secure_router_mod = importlib.import_module("deeptutor.api._secure_router")
    ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
    session_module = importlib.import_module("deeptutor.services.session")
    learner_state_module = importlib.import_module("deeptutor.services.learner_state")
    old_values = {
        "secure_resolve_auth_context": secure_router_mod.resolve_auth_context,
        "secure_rate_limit": secure_router_mod.enforce_websocket_rate_limit,
        "ws_rate_limit": ws_module.enforce_websocket_rate_limit,
        "get_turn_runtime_manager": session_module.get_turn_runtime_manager,
        "get_learner_state_service": learner_state_module.get_learner_state_service,
    }
    runtime = _DeepQuestionRuntime()

    async def _allow_rate_limit(*_args: Any, **_kwargs: Any) -> bool:
        return True

    try:
        secure_router_mod.resolve_auth_context = lambda _authorization: _auth_ctx(USER_ID)
        secure_router_mod.enforce_websocket_rate_limit = _allow_rate_limit
        ws_module.enforce_websocket_rate_limit = _allow_rate_limit
        session_module.get_turn_runtime_manager = lambda: runtime
        learner_state_module.get_learner_state_service = (
            (lambda: learner_state_service)
            if enable_ws_learner_state_writeback
            else (lambda: _NoWriteLearnerStateService())
        )
        yield runtime
    finally:
        secure_router_mod.resolve_auth_context = old_values["secure_resolve_auth_context"]
        secure_router_mod.enforce_websocket_rate_limit = old_values["secure_rate_limit"]
        ws_module.enforce_websocket_rate_limit = old_values["ws_rate_limit"]
        session_module.get_turn_runtime_manager = old_values["get_turn_runtime_manager"]
        learner_state_module.get_learner_state_service = old_values["get_learner_state_service"]
        _restore_modules(fake_module_snapshot)


def _ws_start_payload() -> dict[str, Any]:
    return {
        "type": "start_turn",
        "content": "共用一个开关箱不妥，应采用专用开关箱。请按案例题阅卷标准批改。",
        "capability": "deep_question",
        "language": "zh",
        "config": {
            "followup_question_context": {
                "question_id": "case-p4-ws-readback",
                "question_type": "case",
                "question": "指出事件二中临时用电管理的不妥之处。",
                "correct_answer": (
                    "不妥之处：1.未编制临时用电施工组织设计；2.共用一个开关箱；"
                    "3.插座插头活动连接。正确做法：1.应编制单项施工用电方案；"
                    "2.应采用专用开关箱；3.插头和插座应配套使用，不得活动连接。"
                ),
                "concentration": "临时用电",
            },
        },
    }


def _run_ws_turn(*, learner_state_service: Any, enable_ws_learner_state_writeback: bool) -> dict[str, Any]:
    ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
    with _patched_ws_runtime(
        learner_state_service=learner_state_service,
        enable_ws_learner_state_writeback=enable_ws_learner_state_writeback,
    ) as runtime:
        result_message: dict[str, Any] | None = None
        messages: list[dict[str, Any]] = []
        with TestClient(_build_ws_app(ws_module.router)) as client:
            with client.websocket_connect("/api/v1/ws") as websocket:
                websocket.send_json(_ws_start_payload())
                for _ in range(40):
                    message = websocket.receive_json()
                    messages.append(message)
                    if message.get("type") == "result":
                        result_message = message
                        break
        return {
            "runtime_started_payload": runtime.started_payload or {},
            "messages": messages,
            "result_message": result_message or {},
        }


def _api_readbacks(*, learner_state_service: Any) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    mobile_module = importlib.import_module("deeptutor.api.routers.mobile")
    with _patched_mobile_module(
        mobile_module=mobile_module,
        learner_state_service=learner_state_service,
        user_id=USER_ID,
    ):
        mobile_module.member_service = _LocalMemberService()
        mobile_module.mistake_book_service = _LocalMistakeBookService()
        mobile_module.get_notebook_card_service = lambda: _LocalNotebookCardService()
        with TestClient(_build_mobile_app(mobile_module.router)) as client:
            projection_response = client.get("/api/v1/learning-brain/projection?event_limit=25")
            report_response = client.get("/api/v1/mobile/learning-report?event_limit=25&schema_version=2")
    projection_payload = projection_response.json() if projection_response.status_code == 200 else {}
    report_payload = report_response.json() if report_response.status_code == 200 else {}
    return projection_payload, report_payload, projection_response.status_code, report_response.status_code


def _ws_pair_id(*, turn_id: str, projection_hash: str, report_hash: str, event_ids: list[str]) -> str:
    if not turn_id or not projection_hash or not report_hash or not event_ids:
        return ""
    digest = hashlib.sha256(
        json.dumps(
            {
                "turn_id": turn_id,
                "projection_hash": projection_hash,
                "report_hash": report_hash,
                "event_ids": event_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"ws_api_pair_{digest}"


def build_p4_ws_readback_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    enable_ws_learner_state_writeback: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    local_runtime_root = out / "local_runtime"
    learner_state_service = _local_service(local_runtime_root)
    ws_result = _run_ws_turn(
        learner_state_service=learner_state_service,
        enable_ws_learner_state_writeback=enable_ws_learner_state_writeback,
    )
    result_message = dict(ws_result.get("result_message") or {})
    result_meta = dict(result_message.get("metadata") or {})
    construction_result = dict(result_meta.get("construction_grading_result") or {})
    events = learner_state_service.list_memory_events(USER_ID, limit=None)
    learning_events = [event for event in events if event.memory_kind == "learning_evidence"]
    event_ids = [event.event_id for event in learning_events]

    projection_payload, report_payload, projection_status, report_status = _api_readbacks(
        learner_state_service=learner_state_service
    )
    projection_hash = _output_projection_hash(projection_payload)
    report_hash = _report_projection_hash(report_payload)
    hash_match = bool(projection_hash and report_hash and projection_hash == report_hash)
    turn_id = str(result_message.get("turn_id") or "").strip()
    readback_ids = {
        "turn_id": turn_id,
        "learner_memory_event_id": event_ids[0] if event_ids else "",
        "learning_brain_projection_hash": _sha(projection_payload) if projection_payload else "",
        "mobile_learning_report_hash": _sha(report_payload) if report_payload else "",
        "ws_api_surface_pair_id": _ws_pair_id(
            turn_id=turn_id,
            projection_hash=projection_hash,
            report_hash=report_hash,
            event_ids=event_ids,
        ),
    }

    blockers: list[str] = []
    if not result_message:
        blockers.append("ws_result_event_missing")
    if not construction_result:
        blockers.append("construction_grading_result_missing")
    if not event_ids:
        blockers.append("learner_memory_event_writeback_missing")
    if projection_status != 200 or not projection_hash:
        blockers.append("learning_brain_projection_readback_missing")
    if report_status != 200 or not report_hash:
        blockers.append("mobile_learning_report_readback_missing")
    if projection_hash and report_hash and not hash_match:
        blockers.append("api_projection_hash_mismatch")

    package = {
        "schema_version": "luban_p4_ws_readback_gate.v1",
        "generated_at": "2026-06-12",
        "p4_ws_readback": {
            "verdict": "STRONG-GO" if not blockers else "NO-GO",
            "mode": "local_testclient_ws_readback",
            "scope": "local_fastapi_ws_router_not_real_wechat_not_release_truth",
            "ws_turn_exercised": True,
            "required_readbacks_present": not blockers,
            "projection_hash_match": hash_match,
            "readback_ids": readback_ids,
            "blockers": blockers,
        },
        "ws_turn": {
            "path": "/api/v1/ws",
            "result_event_seen": bool(result_message),
            "turn_id": turn_id,
            "session_id": str(result_message.get("session_id") or ""),
            "construction_grading_result_present": bool(construction_result),
            "construction_grading_result_summary": {
                "authority": construction_result.get("authority"),
                "type": construction_result.get("type"),
                "score_awarded": construction_result.get("score_awarded"),
                "max_score": construction_result.get("max_score"),
            },
            "learner_memory_event_ids": event_ids,
            "message_types": [str(message.get("type") or "") for message in list(ws_result.get("messages") or [])],
        },
        "api_readbacks": {
            "learning_brain_projection": {
                "path": "/api/v1/learning-brain/projection?event_limit=25",
                "status_code": projection_status,
                "output_projection_hash": projection_hash,
                "event_count": projection_payload.get("event_count") if isinstance(projection_payload, dict) else None,
            },
            "mobile_learning_report_v2": {
                "path": "/api/v1/mobile/learning-report?event_limit=25&schema_version=2",
                "status_code": report_status,
                "output_projection_hash": report_hash,
                "authority": dict(report_payload.get("authority") or {}) if isinstance(report_payload, dict) else {},
                "grading_to_brain_loop_present": bool(
                    isinstance(report_payload, dict) and report_payload.get("grading_to_brain_loop")
                ),
            },
        },
        "sources": {
            "ws_surface": "/api/v1/ws",
            "memory_events_source": "LearnerStateService.MEMORY_EVENTS",
            "api_surfaces": [
                "/api/v1/learning-brain/projection",
                "/api/v1/mobile/learning-report?schema_version=2",
            ],
        },
        "local_artifacts": {
            "runtime_root": _artifact_path(local_runtime_root),
            "memory_events_jsonl": _artifact_path(
                local_runtime_root / "learner_state" / USER_ID / "MEMORY_EVENTS.jsonl"
            ),
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "official_score_promotion",
            "real_wechat_package_readback",
            "real_provider_call",
        ],
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
    }
    (out / "ws_result_message.json").write_text(
        json.dumps(result_message, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "learning_brain_projection_api.json").write_text(
        json.dumps(projection_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "mobile_learning_report_v2_api.json").write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "p4_ws_readback_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    package = build_p4_ws_readback_package(output_dir=args.output_dir)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
