"""Capability-layer rubric-v1 case grading (`_grade_case_rubric_v1` + same-source render).

Hermetic: ``load_rubric`` + ``batch_judge_async`` are stubbed (no LLM, no DB). Proves the flag defaults
OFF (legacy answer + payload byte-identical), the qa_/test_ cohort gate, the append-only contract (legacy
``construction_grading_result`` never mutated, official_score_allowed stays False), open-world (no
compiled rubric) signalling, AND that when V1 is on the student-facing ``response`` is rendered from the
very GradingEvent that produced the score (same source). Reuses the runtime-shadow test harness shape.
"""
from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.construction_grading import rubric_grader_v1 as G


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)
    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)


async def _collect_events(run_coro) -> list[StreamEvent]:
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


def _install_grading_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **_kwargs: Any) -> str:
            return "得分：1分（满分3分）。"

    _install_module(monkeypatch, "deeptutor.agents.question.coordinator", AgentCoordinator=FakeCoordinator)
    _install_module(monkeypatch, "deeptutor.agents.question.agents.submission_grader_agent",
                    SubmissionGraderAgent=FakeSubmissionGraderAgent)
    _install_module(monkeypatch, "deeptutor.services.llm.config",
                    get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"))


def _case_context(*, user_id: str = "qa_case_rubric_v1", rubric_v1: bool = False) -> UnifiedContext:
    raw_answer = "我的答案：共用一个开关箱不妥，应采用专用开关箱。"
    metadata: dict[str, Any] = {
        "user_id": user_id,
        "raw_user_message": raw_answer,
        "conversation_context_text": "用户刚做完一道案例题。",
        "turn_semantic_decision": {"next_action": "route_to_grading"},
        "question_followup_action": {
            "intent": "answer_questions",
            "answers": [{"question_id": "case-9006", "answer": raw_answer}],
        },
        "question_followup_context": {
            "question_id": "case-9006",
            "question": "指出事件二中临时用电管理的不妥之处。",
            "question_type": "case",
            "correct_answer": "不妥之处：共用一个开关箱。正确做法：应采用专用开关箱。",
            "concentration": "临时用电",
        },
    }
    if rubric_v1:
        metadata["grading_engine_case_rubric_v1"] = True
    return UnifiedContext(
        user_message=f"[History Context]\n刚做完题。\n\n[User Question]\n{raw_answer}",
        language="zh",
        metadata=metadata,
    )


async def _run_case(monkeypatch: pytest.MonkeyPatch, context: UnifiedContext) -> dict[str, Any]:
    _install_grading_fakes(monkeypatch)
    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))
    return next(event.metadata for event in events if event.type == StreamEventType.RESULT)


_RUBRIC = [
    {"point_id": "P1", "text": "共用一个开关箱不妥", "score": 1.0, "policy": "boolean_judgment", "required_terms": []},
    {"point_id": "P2", "text": "应采用专用开关箱", "score": 1.0, "policy": "list", "required_terms": []},
    {"point_id": "P3", "text": "应编制临时用电方案", "score": 1.0, "policy": "list", "required_terms": []},
]


@pytest.mark.asyncio
async def test_case_rubric_v1_absent_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default OFF -> legacy untouched, no v1 key. Stub the grader to explode if it ever runs.
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")))
    result = await _run_case(monkeypatch, _case_context(rubric_v1=False))
    assert result["construction_grading_result"]["authority"] == "construction_grading"
    assert "luban_case_rubric_v1" not in result
    # legacy answer path (the fake SubmissionGraderAgent) — V1 did NOT take over the response
    assert result["response"] == "得分：1分（满分3分）。"


@pytest.mark.asyncio
async def test_case_rubric_v1_grades_for_qa_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))

    legacy = result["construction_grading_result"]
    v1 = result["luban_case_rubric_v1"]
    assert legacy["authority"] == "construction_grading"          # legacy intact (separate from v1)
    assert legacy["type"] == "case"
    assert v1["status"] == "ok"
    assert v1["official_score_allowed"] is False                  # never official
    assert v1["grading_event"]["awarded_score"] == 2.0           # P1+P2 hit, P3 miss
    assert v1["grading_event"]["max_score"] == 3.0
    weak = {w["concept_label"] for w in v1["learning_evidence"]["weak_points"]}
    assert "应编制临时用电方案" in weak                            # the missed point -> weak point
    assert v1["learning_evidence"]["writeback_performed"] is False
    # SAME-SOURCE: the student-facing response is rendered from this very event (not the V0 agent)
    resp = result["response"]
    assert "逐采分点点评" in resp and "【得分】2.0 / 3.0 分" in resp
    assert resp != "得分：1分（满分3分）。"                        # V1 took over the answer


@pytest.mark.asyncio
async def test_case_rubric_v1_non_qa_student_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")))
    result = await _run_case(monkeypatch, _case_context(user_id="real_student_1", rubric_v1=True))
    assert result["construction_grading_result"]["authority"] == "construction_grading"
    assert "luban_case_rubric_v1" not in result


@pytest.mark.asyncio
async def test_case_rubric_v1_open_world_no_rubric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [])  # not in bank -> open world
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    assert result["luban_case_rubric_v1"]["status"] == "no_rubric_open_world"
    assert result["construction_grading_result"]["authority"] == "construction_grading"


@pytest.mark.asyncio
async def test_case_rubric_v1_env_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Env kill switch force-disables even with the request flag on.
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "false")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")))
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    assert "luban_case_rubric_v1" not in result


def test_batch_judge_async_parses_and_fails_closed() -> None:
    async def _ok_complete(**_kwargs):
        return '[{"point_id":"P1","status":"hit"},{"point_id":"P2","status":"miss"}]'

    async def _boom_complete(**_kwargs):
        raise RuntimeError("llm down")

    verdicts = asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _ok_complete, "k"))
    assert verdicts["P1"]["status"] == "hit" and verdicts["P2"]["status"] == "miss"
    # failure -> empty dict -> grade_with_rubric treats every point as miss+low_conf
    assert asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _boom_complete, "k")) == {}
