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
async def test_case_rubric_v1_kill_switch_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    # V1 is DEFAULT ON (full rollout); the emergency env kill switch disables it -> legacy untouched.
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "false")
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
    assert v1["grading_event"]["rubric_provenance"] == "compiled_rubric"  # in-bank ammunition used
    weak = {w["concept_label"] for w in v1["learning_evidence"]["weak_points"]}
    assert "应编制临时用电方案" in weak                            # the missed point -> weak point
    assert v1["learning_evidence"]["writeback_performed"] is False
    # SAME-SOURCE: the student-facing response is rendered from this very event (not the V0 agent)
    resp = result["response"]
    assert "逐采分点点评" in resp and "【得分】2.0 / 3.0 分" in resp
    assert resp != "得分：1分（满分3分）。"                        # V1 took over the answer
    # SAME-SOURCE outcome: is_correct derived from the V1 event (2/3 partial -> not full -> not correct),
    # so recent_outcomes / projection record what the student actually read.
    assert result["is_correct"] is False


@pytest.mark.asyncio
async def test_case_rubric_v1_all_users_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # full rollout (not gray): even a non-qa student, with NO per-turn flag, gets V1 by default.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.MISS}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    result = await _run_case(monkeypatch, _case_context(user_id="real_student_1", rubric_v1=False))
    assert result["luban_case_rubric_v1"]["status"] == "ok"     # non-qa, no flag -> still graded
    assert "逐采分点点评" in result["response"]


@pytest.mark.asyncio
async def test_case_rubric_v1_open_world_extracts_and_grades(monkeypatch: pytest.MonkeyPatch) -> None:
    # NEXUS-like: not in the compiled bank -> extract scoring points on-the-fly from the question's
    # own reference answer and STILL grade with V1 (never fall back to V0's deterministic keywords).
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [])  # not in bank

    captured_ref = {}

    async def _fake_extract(reference, stem, complete_fn, api_key, *, model="deepseek-chat"):
        captured_ref["reference"] = reference
        return [{"point_id": "P1", "text": "应采用专用开关箱", "score": 1.0, "policy": "list",
                 "required_terms": []},
                {"point_id": "P2", "text": "应编制临时用电方案", "score": 1.0, "policy": "list",
                 "required_terms": []}]

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.MISS}}

    monkeypatch.setattr(G, "extract_rubric_from_reference_async", _fake_extract)
    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    v1 = result["luban_case_rubric_v1"]
    ev = v1["grading_event"]
    assert v1["status"] == "ok"                                          # open world STILL grades
    assert ev["rubric_provenance"] == "on_the_fly_reference"
    # P1 hit, P2 miss; equal-weight points -> hit earns exactly half the (normalized) max, regardless
    # of the nominal scale the open-world weights were normalized to.
    assert ev["max_score"] > 0 and abs(ev["awarded_score"] - ev["max_score"] / 2) < 0.01
    assert "共用一个开关箱" in captured_ref["reference"]                  # extracted from THIS question's ref
    assert "逐采分点点评" in result["response"]                          # student sees V1, not V0


@pytest.mark.asyncio
async def test_case_rubric_v1_global_on_bypasses_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    # LUBAN_CASE_RUBRIC_V1_ENABLED=true -> on for everyone on the instance, even a non-qa account
    # (dev/local). No per-turn flag needed.
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.MISS}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    # real_student_1 is NOT in the qa_/test_ cohort, but global-on overrides it
    result = await _run_case(monkeypatch, _case_context(user_id="real_student_1", rubric_v1=False))
    assert result["luban_case_rubric_v1"]["status"] == "ok"
    assert "逐采分点点评" in result["response"]


@pytest.mark.asyncio
async def test_case_rubric_v1_env_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Env kill switch force-disables even with the request flag on.
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "false")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")))
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    assert "luban_case_rubric_v1" not in result


def test_grade_case_batch_v1_grades_each_case_item(monkeypatch: pytest.MonkeyPatch) -> None:
    # Multi-item turn (type=="batch"): each case sub-item is graded by the SAME V1 core and merged into
    # one case_grading_completed event with summed scores. Non-case items are skipped.
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [
        {"point_id": "P1", "text": "点1", "score": 1.0, "policy": "list", "required_terms": []},
        {"point_id": "P2", "text": "点2", "score": 1.0, "policy": "list", "required_terms": []},
    ])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    graded_context = {
        "construction_grading_result": {"type": "batch"},
        "items": [
            {"question_id": "c1", "user_answer": "a1",
             "construction_grading_result": {"type": "case", "max_score": 2.0}},
            {"question_id": "c2", "user_answer": "a2",
             "construction_grading_result": {"type": "case", "max_score": 2.0}},
            {"question_id": "m1", "user_answer": "C",
             "construction_grading_result": {"type": "mcq"}},  # skipped
        ],
    }

    async def _noop_complete(**_kw):
        return "{}"

    ev = asyncio.run(dq._grade_case_batch_v1(
        graded_context, student_id="qa_x", complete=_noop_complete, key="k", _G=G))
    assert ev["event_type"] == "case_grading_completed"
    assert len(ev["items"]) == 2                       # 2 case items graded, mcq skipped
    assert ev["max_score"] == 4.0                      # 2 + 2
    assert ev["awarded_score"] == 2.0                  # each item P1 hit (1.0) -> 1+1
    assert ev["rubric_provenance"] == "batch"
    assert ev["official_score_allowed"] is False


def test_batch_judge_async_parses_and_fails_closed() -> None:
    async def _ok_complete(**_kwargs):
        return '[{"point_id":"P1","status":"hit"},{"point_id":"P2","status":"miss"}]'

    async def _boom_complete(**_kwargs):
        raise RuntimeError("llm down")

    verdicts = asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _ok_complete, "k"))
    assert verdicts["P1"]["status"] == "hit" and verdicts["P2"]["status"] == "miss"
    # failure -> empty dict -> grade_with_rubric treats every point as miss+low_conf
    assert asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _boom_complete, "k")) == {}
