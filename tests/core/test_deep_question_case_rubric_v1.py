"""Capability-layer rubric-v1 case grading (`_grade_case_rubric_v1` + same-source render).

Hermetic: ``load_rubric`` + ``batch_judge_async`` are stubbed (no LLM, no DB). Proves V1 is DEFAULT ON
(full rollout) with only an env kill switch, the fail-safe degraded fallback (no trustworthy verdict ->
legacy diagnostic, never a fake 0/full), the append-only contract (legacy ``construction_grading_result``
never mutated, official_score_allowed stays False), open-world (no compiled rubric) signalling, AND that
when V1 is on the student-facing ``response`` is rendered from the very GradingEvent that produced the
score (same source). Reuses the runtime-shadow test harness shape.
"""
from __future__ import annotations

import asyncio
import re
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
    assert "## 整体评价" in resp and "得分预估：** 2 / 3 分" in resp
    assert "**采分点：**" in resp
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
    assert "## 整体评价" in result["response"]


@pytest.mark.asyncio
async def test_case_rubric_v1_open_world_extracts_and_grades(monkeypatch: pytest.MonkeyPatch) -> None:
    # NEXUS-like: not in the compiled bank -> extract scoring points on-the-fly from the question's
    # own reference answer and STILL grade with V1 (never fall back to V0's deterministic keywords).
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [])  # not in bank

    captured_ref = {}

    async def _fake_extract(
        reference,
        stem,
        complete_fn,
        api_key,
        *,
        model="deepseek-chat",
        provider_authority="",
    ):
        captured_ref["reference"] = reference
        captured_ref["provider_authority"] = provider_authority
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
    assert captured_ref["provider_authority"] == "deepseek:https://api.deepseek.com"
    assert "## 整体评价" in result["response"]                          # student sees V1, not V0


@pytest.mark.asyncio
async def test_case_rubric_v1_stem_only_surfaces_diagnostic_score_without_official_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No compiled rubric and no explicit answer key: V1 should still help the learner by deriving
    # diagnostic scoring points from THIS stem, while keeping official_score_allowed false.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [])

    context = _case_context(rubric_v1=True)
    followup_context = dict(context.metadata["question_followup_context"])
    followup_context.pop("correct_answer", None)
    context.metadata["question_followup_context"] = followup_context

    async def _fake_derive(*_args, **_kwargs):
        return [
            {"point_id": "P1", "text": "共用一个开关箱不妥", "score": 1.0,
             "policy": "qualitative", "required_terms": []},
            {"point_id": "P2", "text": "应采用专用开关箱", "score": 1.0,
             "policy": "qualitative", "required_terms": []},
        ]

    async def _fake_score(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT, "evidence_span": "共用一个开关箱不妥"},
                "P2": {"status": G.MISS}}

    monkeypatch.setattr(G, "derive_rubric_from_stem_async", _fake_derive)
    monkeypatch.setattr(G, "batch_judge_async", _fake_score)

    result = await _run_case(monkeypatch, context)
    payload = result.get("luban_case_rubric_v1") or {}
    assert payload.get("status") == "ok"
    assert payload.get("official_score_allowed") is False
    assert payload["grading_event"]["rubric_provenance"] == "derived_from_stem"
    assert payload["grading_event"]["answer_key_authority"] == "derived_from_stem_pending_calibration"
    assert payload["grading_event"]["high_risk_review"] is True
    assert "## 整体评价" in result["response"]
    assert "诊断得分预估" in result["response"]
    assert "未命中题库原题/标准答案" in result["response"]


@pytest.mark.asyncio
async def test_case_rubric_v1_degraded_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    # FAIL-SAFE: when the batch LLM produces NO trustworthy verdict (call down / JSON malformed -> empty
    # verdicts), V1 must NOT surface a 0/full score as authority. It returns a degraded marker so the turn
    # falls back to the legacy diagnostic path — never a fake "0 分".
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _empty_verdicts(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {}  # LLM down / malformed -> no verdict for any point

    monkeypatch.setattr(G, "batch_judge_async", _empty_verdicts)
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    # V1 does NOT take over: no authoritative payload, student does not see a "0/满分" V1 render.
    payload = result.get("luban_case_rubric_v1")
    assert payload is None or payload.get("status") != "ok"
    assert "逐采分点点评" not in result["response"]


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
    # real per-sub-question identity preserved (NOT the literal "batch") so learning-evidence provenance
    # is true, not a placeholder.
    assert ev["question_id"] == "c1,c2"
    assert {sp["source_qid"] for sp in ev["scoring_points"]} == {"c1", "c2"}


def test_grade_case_batch_v1_all_degraded_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # If EVERY case sub-item degrades (no trustworthy verdict), the batch yields no graded sub-event ->
    # None -> caller falls back to legacy (never a merged 0/full).
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [
        {"point_id": "P1", "text": "点1", "score": 1.0, "policy": "list", "required_terms": []}])

    async def _empty(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {}

    monkeypatch.setattr(G, "batch_judge_async", _empty)

    async def _noop_complete(**_kw):
        return "{}"

    graded_context = {
        "construction_grading_result": {"type": "batch"},
        "items": [{"question_id": "c1", "user_answer": "a1",
                   "construction_grading_result": {"type": "case", "max_score": 2.0}}],
    }
    ev = asyncio.run(dq._grade_case_batch_v1(
        graded_context, student_id="qa_x", complete=_noop_complete, key="k", _G=G))
    assert ev is None


def test_grade_case_batch_v1_partial_degraded_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # FAIL-SAFE: if ANY case sub-item degrades, the whole batch must fall back to legacy — NEVER surface a
    # "complete" merged score built from only the survivors (a half-graded case shown as 100% is worse
    # than a low score). c1 grades, c2 degrades (empty verdicts) -> batch returns None.
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [
        {"point_id": "P1", "text": "点1", "score": 1.0, "policy": "list", "required_terms": []}])

    async def _c1_ok_c2_empty(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}} if answer == "a1" else {}   # c2 -> no verdict -> degraded

    monkeypatch.setattr(G, "batch_judge_async", _c1_ok_c2_empty)

    async def _noop_complete(**_kw):
        return "{}"

    graded_context = {
        "construction_grading_result": {"type": "batch"},
        "items": [{"question_id": "c1", "user_answer": "a1",
                   "construction_grading_result": {"type": "case", "max_score": 2.0}},
                  {"question_id": "c2", "user_answer": "a2",
                   "construction_grading_result": {"type": "case", "max_score": 2.0}}],
    }
    ev = asyncio.run(dq._grade_case_batch_v1(
        graded_context, student_id="qa_x", complete=_noop_complete, key="k", _G=G))
    assert ev is None   # partial batch -> legacy, not a misleading "c1-only 100%"


def test_batch_judge_async_parses_and_fails_closed() -> None:
    # LLM returns SHORT idx (1..n); batch_judge maps them back to real point_ids (so long compound ids
    # never need verbatim echo — eliminating the truncation/mismatch hazard).
    async def _ok_complete(**_kwargs):
        return '[{"idx":1,"status":"hit"},{"idx":2,"status":"miss"}]'

    async def _boom_complete(**_kwargs):
        raise RuntimeError("llm down")

    verdicts = asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _ok_complete, "k"))
    assert verdicts["P1"]["status"] == "hit" and verdicts["P2"]["status"] == "miss"
    # failure -> empty dict -> grade_with_rubric treats every point as miss+low_conf
    assert asyncio.run(G.batch_judge_async(_RUBRIC, "ans", _boom_complete, "k")) == {}


def _pgo_ctx(*, flag: bool = True, user_id: str = "qa_pgo_shadow") -> UnifiedContext:
    metadata: dict[str, Any] = {"user_id": user_id}
    if flag:
        metadata["grading_engine_pgo_shadow"] = True
    return UnifiedContext(session_id="s", user_message="m", metadata=metadata)


def _pgo_contract() -> dict[str, Any]:
    return {
        "question_id": "case-pgo",
        "official_total_score": 10.0,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "scoring_points": [
            {"point_id": "p1", "sub_type": "free_text_point", "official_slice": "点1", "score": None},
            {"point_id": "p2", "sub_type": "free_text_point", "official_slice": "点2", "score": None},
        ],
        "supporting_citations": [],
    }


def test_pgo_shadow_flag_off_is_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    payload = {"construction_grading_result": {"score_awarded": 7.0, "max_score": 10.0}}
    before = dict(payload)

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=False),
        graded_context={"pgo_grading_contract": _pgo_contract(), "pgo_point_verdicts": {"p1": "hit"}},
        result_payload=payload,
    )

    assert payload == before


def test_pgo_shadow_env_default_off_kills_even_with_request_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.delenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", raising=False)
    payload = {"construction_grading_result": {"score_awarded": 7.0, "max_score": 10.0}}

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True),
        graded_context={"pgo_grading_contract": _pgo_contract(), "pgo_point_verdicts": {"p1": "hit"}},
        result_payload=payload,
    )

    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert shadow["shadow_status"] == "killed_by_switch"
    assert shadow["writeback_performed"] is False
    assert payload["construction_grading_result"]["score_awarded"] == 7.0


def test_pgo_shadow_append_only_uses_official_total_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    legacy = {"score_awarded": 7.0, "max_score": 10.0, "authority": "construction_grading"}
    payload = {"construction_grading_result": dict(legacy)}

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True, user_id="operator_pgo"),
        graded_context={
            "question_id": "case-pgo",
            "pgo_grading_contract": _pgo_contract(),
            "pgo_point_verdicts": {"p1": "hit", "p2": "partial"},
        },
        result_payload=payload,
    )

    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert payload["construction_grading_result"] == legacy
    assert shadow["authority"] == "luban_case_rubric_pgo_shadow"
    assert shadow["shadow_status"] == "ok"
    assert shadow["score"]["awarded_score"] == 7.5
    assert shadow["score"]["max_score"] == 10.0
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False
    assert shadow["runtime_points"][0]["score"] is None


def test_pgo_shadow_consumes_retrieve_rubric_without_leaking_official_slice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.capabilities import deep_question as dq
    from deeptutor.services.construction_grading import m35_artifact_query

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    legacy = {"score_awarded": 7.0, "max_score": 10.0, "authority": "construction_grading"}
    payload = {"construction_grading_result": dict(legacy)}
    calls = []

    def _fake_retrieve(query):
        calls.append(query)
        return {
            "found": True,
            "question_id": query.question_id,
            "artifact_version": "case_rubric_scored_pgo",
            "purpose": query.purpose,
            "shape": query.shape,
            "budget": {"tier": query.budget_tier, "runtime": "deterministic_pgo_supply"},
            "ground": {"source_ref_count": 2, "citation_required": query.citation_required},
            "confidence": {
                "verdict_ceiling": "release_candidate_review_only",
                "published": False,
                "production_default": "off",
            },
            "scoring_points": [
                {
                    "point_id": "p1",
                    "official_slice": "THIS OFFICIAL ANSWER MUST NOT LEAK",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                }
            ],
        }

    monkeypatch.setattr(m35_artifact_query, "retrieve_rubric", _fake_retrieve)

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True, user_id="operator_pgo"),
        graded_context={
            "question_id": "case-pgo",
            "pgo_grading_contract": _pgo_contract(),
            "pgo_point_verdicts": {"p1": "hit", "p2": "partial"},
        },
        result_payload=payload,
    )

    assert payload["construction_grading_result"] == legacy
    assert len(calls) == 1
    assert calls[0].question_id == "case-pgo"
    assert calls[0].purpose == "grading"
    assert calls[0].shape == "rubric_table"
    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert shadow["knowql_query"]["executor"] == "retrieve_rubric"
    assert shadow["knowql_query"]["runtime_consumed"] is True
    assert shadow["knowql_query"]["found"] is True
    assert shadow["knowql_query"]["scoring_point_count"] == 1
    assert "official_slice" not in str(shadow["knowql_query"])
    assert "THIS OFFICIAL ANSWER MUST NOT LEAK" not in str(shadow)
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False


def test_pgo_shadow_redacts_contract_official_slices_from_client_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.capabilities import deep_question as dq
    from deeptutor.services.construction_grading import m35_artifact_query

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")

    def _fake_retrieve(query):
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "artifact_missing",
        }

    monkeypatch.setattr(m35_artifact_query, "retrieve_rubric", _fake_retrieve)
    contract = _pgo_contract()
    contract["scoring_points"][0]["official_slice"] = "HIDDEN CONTRACT SLICE"
    payload = {"construction_grading_result": {"score_awarded": 7.0, "max_score": 10.0}}

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True, user_id="operator_pgo"),
        graded_context={
            "question_id": "case-pgo",
            "pgo_grading_contract": contract,
            "pgo_point_verdicts": {"p1": "hit", "p2": "partial"},
        },
        result_payload=payload,
    )

    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert "HIDDEN CONTRACT SLICE" not in str(shadow)
    assert "official_slice" not in str(shadow.get("runtime_points", []))
    assert "knowledge_point" not in str(shadow.get("runtime_points", []))
    assert shadow["score"]["max_score"] == 10.0
    assert shadow["writeback_performed"] is False


def test_pgo_shadow_records_retrieve_rubric_fail_open_without_mutating_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.capabilities import deep_question as dq
    from deeptutor.services.construction_grading import m35_artifact_query

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    legacy = {"score_awarded": 7.0, "max_score": 10.0, "authority": "construction_grading"}
    payload = {"construction_grading_result": dict(legacy)}

    def _fake_retrieve(query):
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "runtime_supply_unavailable",
            "blockers": ["content_hash_mismatch"],
        }

    monkeypatch.setattr(m35_artifact_query, "retrieve_rubric", _fake_retrieve)

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True, user_id="operator_pgo"),
        graded_context={
            "question_id": "case-pgo",
            "pgo_grading_contract": _pgo_contract(),
            "pgo_point_verdicts": {"p1": "hit", "p2": "partial"},
        },
        result_payload=payload,
    )

    assert payload["construction_grading_result"] == legacy
    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert shadow["knowql_query"]["runtime_consumed"] is True
    assert shadow["knowql_query"]["fail_open"] is True
    assert shadow["knowql_query"]["reason"] == "runtime_supply_unavailable"
    assert shadow["knowql_query"]["blockers"] == ["content_hash_mismatch"]
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False


def test_pgo_shadow_consumes_real_hash_pinned_supply_as_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    known_qid = "2015::EXAM_XW2015_CASE_1::E0"
    contract = _pgo_contract()
    contract["question_id"] = known_qid
    payload = {
        "construction_grading_result": {
            "score_awarded": 7.0,
            "max_score": 10.0,
            "authority": "construction_grading",
        }
    }

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True, user_id="operator_pgo"),
        graded_context={
            "question_id": known_qid,
            "pgo_grading_contract": contract,
            "pgo_point_verdicts": {"p1": "hit", "p2": "partial"},
        },
        result_payload=payload,
    )

    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert shadow["knowql_query"]["runtime_consumed"] is True
    assert shadow["knowql_query"]["found"] is True
    assert shadow["knowql_query"]["artifact_version"] == "case_rubric_scored_pgo"
    assert shadow["knowql_query"]["scoring_point_count"] > 0
    assert "official_slice" not in str(shadow["knowql_query"])
    assert "answer_key_authority" not in str(shadow)
    assert shadow["official_score_allowed"] is False
    assert shadow["canonical_write_allowed"] is False
    assert shadow["writeback_performed"] is False


def test_pgo_shadow_missing_contract_fails_closed_without_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.setenv("LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED", "true")
    payload = {"construction_grading_result": {"score_awarded": 7.0, "max_score": 10.0}}

    dq._maybe_attach_pgo_shadow(
        context=_pgo_ctx(flag=True),
        graded_context={"pgo_point_verdicts": {"p1": "hit"}},
        result_payload=payload,
    )

    shadow = payload["luban_case_rubric_pgo_shadow"]
    assert shadow["shadow_status"] == "pgo_contract_missing"
    assert shadow["writeback_performed"] is False
    assert shadow["runtime_points"] == []


@pytest.mark.asyncio
async def test_case_rubric_v1_g2_guard_demotes_rich_leaf_point(monkeypatch: pytest.MonkeyPatch) -> None:
    # G2 single-authority WIRED on the live scoring path: if a rich-leaf / textbook-cited point ever
    # appears in the rubric, it is demoted to supporting BEFORE the judge sees it and NEVER scores —
    # only official-answer-backed points do. The 50x-volume rich-leaf points cannot impersonate the key.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    rubric_with_rich_leaf = _RUBRIC + [
        {"point_id": "RL1", "text": "教材引证(supporting)", "score": 5.0, "policy": "list",
         "required_terms": [], "authority_source": "textbook_cited"},
    ]
    monkeypatch.setattr(G, "load_rubric", lambda qid: rubric_with_rich_leaf if qid == "case-9006" else [])

    seen: dict[str, Any] = {}

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        seen["ids"] = [p.get("point_id") for p in points]
        seen["points"] = [dict(p) for p in points]
        return {p.get("point_id"): {"status": G.HIT} for p in points}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    v1 = result["luban_case_rubric_v1"]
    # the rich-leaf point never reached the judge (demoted by the G2 guard) and never scored
    assert "RL1" not in seen["ids"]
    assert set(seen["ids"]) == {"P1", "P2", "P3"}
    graded_ids = {p["point_id"] for p in v1["grading_event"]["scoring_points"]}
    assert "RL1" not in graded_ids
    # max_score reflects only the 3 official points (3.0), NOT the 5.0 rich-leaf point
    assert v1["grading_event"]["max_score"] == 3.0
    # canonical typed object is WIRED onto the live path: canonicalize_rubric_points stamped the
    # canonical authority_source on every official point BEFORE G2 (that stamp is what armed the G2
    # demotion above — the foundation is genuinely live, not a no-op).
    assert all(p.get("authority_source") for p in seen["points"])


def test_summarize_pgo_query_result_consumes_scorable_for_coverage():
    # Consumer must ACT on per-point `scorable`, not just pass the field through:
    # it separates the gradable denominator from the raw point count so a shadow's
    # coverage never silently includes supporting/unsourced points.
    from deeptutor.capabilities.deep_question import _summarize_pgo_query_result

    result = {
        "found": True,
        "question_id": "Q-MIX",
        "scoring_points": [
            {"point_id": "a", "scorable": True},
            {"point_id": "b", "scorable": False},
            {"point_id": "c", "scorable": False},
        ],
        "ground": {"score_bearing_count": 1, "supporting_count": 1, "unsourced_count": 1},
    }

    summary = _summarize_pgo_query_result(result)

    assert summary["scoring_point_count"] == 3
    assert summary["scorable_point_count"] == 1
    assert summary["has_unscorable_points"] is True


def test_summarize_pgo_query_result_all_scorable_flags_no_unscorable():
    from deeptutor.capabilities.deep_question import _summarize_pgo_query_result

    result = {
        "found": True,
        "scoring_points": [
            {"point_id": "a", "scorable": True},
            {"point_id": "b", "scorable": True},
        ],
    }

    summary = _summarize_pgo_query_result(result)

    assert summary["scoring_point_count"] == 2
    assert summary["scorable_point_count"] == 2
    assert summary["has_unscorable_points"] is False


@pytest.mark.asyncio
async def test_case_rubric_v1_score_total_mismatch_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2 分值对账（1b 一致性闸观测期，best-effort 非 blocking）：编译 rubric 总分与
    题面名义分显著分歧 = qid 可能错绑到别的小问 → event 落
    ``case_rubric_score_total_mismatch`` marker 发声；一致时无 marker（观测对称）。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)

    # rubric 总分 3.0 vs 名义 10 分 → 发声
    event = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "共用开关箱不妥",
         "construction_grading_result": {"type": "case", "max_score": 10}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["event_type"] == "case_grading_completed"
    assert event["case_rubric_score_total_mismatch"] is True

    # rubric 总分 3.0 vs 名义 3 分 → 无 marker
    event_ok = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "共用开关箱不妥",
         "construction_grading_result": {"type": "case", "max_score": 3}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event_ok["event_type"] == "case_grading_completed"
    assert "case_rubric_score_total_mismatch" not in event_ok


@pytest.mark.asyncio
async def test_case_rubric_v1_event_carries_bank_slot_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """护栏③：判分事件逐轮携带活动 bank 身份（slot:governance:qid_count）——slot
    未授权漂移六周无人知的洞，用导出封死。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])
    monkeypatch.setattr(
        G, "active_bank_identity",
        lambda: {"slot": "legacy", "qid_count": 174, "governance": "authorized"},
    )

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    event = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "共用开关箱不妥",
         "construction_grading_result": {"type": "case", "max_score": 3}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["event_type"] == "case_grading_completed"
    assert event["case_rubric_bank_slot"] == "legacy:authorized:174"


@pytest.mark.asyncio
async def test_case_rubric_v1_point_pool_exceeds_max_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """踩点封顶观测（裁决②）：Σ点分池>小题满分（真题常态，2025案例4 Σ30/满20）时
    落 point_pool_exceeds_max=超额量；池≤满分不落。observe-only，分数行为不变。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    # 池 Σ=3.0 > 满分 2 → 超额 1.0
    event = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "作答",
         "construction_grading_result": {"type": "case", "max_score": 2}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["point_pool_exceeds_max"] == 1.0
    # 池=满分 → 无 marker
    event_ok = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "作答",
         "construction_grading_result": {"type": "case", "max_score": 3}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert "point_pool_exceeds_max" not in event_ok


@pytest.mark.asyncio
async def test_case_rubric_v1_mnemonic_source_marker_on_render_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A1 真口诀（拍A）：deep_question 渲染路径必须给 grading_event 落
    case_mnemonic_source 发声——解析不中=fallback_template（宁缺勿错挂的回落面）。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])
    monkeypatch.setattr(G, "resolve_case_answer_method_for_render", lambda stem: None)

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    result = await _run_case(monkeypatch, _case_context(rubric_v1=True))
    event = result["luban_case_rubric_v1"]["grading_event"]
    assert event["case_mnemonic_source"] == "fallback_template"


@pytest.mark.asyncio
async def test_case_rubric_v1_event_carries_subq_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """覆盖对账（live 事故：答 2/4 问被判整题满分）：judging 事件必须携带
    case_subq_coverage/uncovered/声明，供渲染双面与全 sink 同源消费。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    rubric = [
        {"point_id": "P1", "question_no": 1, "text": "见证记录", "score": 1.0,
         "policy": "list", "required_terms": []},
        {"point_id": "P2", "question_no": 4, "text": "工艺流程", "score": 1.0,
         "policy": "list", "required_terms": []},
    ]
    monkeypatch.setattr(G, "load_rubric", lambda qid: rubric if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    stem = (
        "【背景资料】某工程。\n【问题】\n问题1：指出不妥？\n问题2：缺陷名称？\n"
        "问题3：构造名称？\n问题4：工艺流程？"
    )
    event = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "见证记录相关作答",
         "question_stem": stem,
         "construction_grading_result": {"type": "case", "max_score": 2}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["case_subq_coverage"] == "2/4"
    assert event["case_subq_uncovered"] == "2,3"
    assert "未纳入本次判分" in event["case_subq_coverage_note"]


@pytest.mark.asyncio
async def test_case_rubric_v1_coverage_uses_user_stem_over_bank_stem(monkeypatch: pytest.MonkeyPatch) -> None:
    """覆盖对账基准（live 盲区）：ctx 带 user_stem（学生所见 4 问整题面）而
    question_stem 是单小问 bank 行时，覆盖必须按 user_stem 对账并落声明。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    rubric = [{"point_id": "P1", "question_no": 1, "text": "见证记录", "score": 1.0,
               "policy": "list", "required_terms": []}]
    monkeypatch.setattr(G, "load_rubric", lambda qid: rubric if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)
    event = await _grade_one_case_v1(
        {"question_id": "case-9006", "user_answer": "作答",
         "question_stem": "【背景】某工程。\n问题1：指出不妥？",  # 单小问 bank 行
         "user_stem": ("【背景】某工程。\n问题1：指出不妥？\n问题2：名称？\n"
                        "问题3：构造？\n问题4：流程？"),
         "construction_grading_result": {"type": "case", "max_score": 1}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["case_subq_coverage"] == "1/4"
    assert event["case_subq_uncovered"] == "2,3,4"
    assert "未纳入本次判分" in event["case_subq_coverage_note"]


@pytest.mark.asyncio
async def test_case_rubric_v1_core_stem_fallback_from_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    """OD-004 根治（共享判分核兜底）：ctx 无 reference 也无 question_stem（agent-loop
    侧入口的 graded_context 形态）时，若学生提交文本本身是案例题面，必须用它
    推导 tier3 而非整条 no_reference 降级——判分行为在场必须有判分基座。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])
    derived = [{"point_id": "D1", "text": "专家论证", "score": 1.0, "policy": "list", "required_terms": []}]
    seen = {}

    async def _fake_derive(stem, complete_fn, api_key, *, model="deepseek-chat",
                           provider_authority="", kb_evidence=None):
        seen["stem"] = stem
        return list(derived)

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"D1": {"status": G.HIT}}

    monkeypatch.setattr(G, "derive_rubric_from_stem_async", _fake_derive)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)

    paste = ("【背景资料】某工程基坑开挖深度8米，施工单位编制方案。" + "补充描述" * 25 +
             "\n【问题】1. 指出不妥之处？2. 正确做法？\n我认为需要专家论证。")
    event = await _grade_one_case_v1(
        {"question_id": "", "user_answer": paste, "question_stem": "", "correct_answer": "",
         "construction_grading_result": {"type": "case", "max_score": 10}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event.get("event_type") == "case_grading_completed"
    assert event.get("case_stem_fallback") == "submission_text"
    assert event.get("rubric_provenance") == "derived_from_stem"
    assert "【问题】" in seen["stem"]

    # 非案例形状短文本 → 仍 no_reference（不制造假判分面）
    ev2 = await _grade_one_case_v1(
        {"question_id": "", "user_answer": "这题怎么做？", "question_stem": "", "correct_answer": "",
         "construction_grading_result": {"type": "case", "max_score": 10}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert ev2.get("status") == "no_reference"


@pytest.mark.asyncio
async def test_case_rubric_v1_stem_fallback_on_real_paper_form(monkeypatch: pytest.MonkeyPatch) -> None:
    """OD-004 终修 domain test：真实考卷粘贴形态（无括号锚、半角「问题:」+提交
    标记）必须触发共享判分核的基座兜底，而非 no_reference 整条降级。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])
    seen = {}

    async def _fake_derive(stem, complete_fn, api_key, *, model="deepseek-chat",
                           provider_authority="", kb_evidence=None):
        seen["stem"] = stem
        return [{"point_id": "D1", "text": "安全交底", "score": 1.0, "policy": "list", "required_terms": []}]

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"D1": {"status": G.HIT}}

    monkeypatch.setattr(G, "derive_rubric_from_stem_async", _fake_derive)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)

    real_paper = (
        "某办公楼工程，地下二层，地上16层，建筑面积3.6万平方米，现浇钢筋混凝土框架剪力墙结构。"
        + "施工过程描述内容补充。" * 12
        + "\n问题:\n1. 指出项目部做法中的不妥之处并说明理由。\n2. 写出正确做法。\n"
        "【我的作答】\n问题1：安全交底不妥。"
    )
    event = await _grade_one_case_v1(
        {"question_id": "", "user_answer": real_paper, "question_stem": "", "correct_answer": "",
         "construction_grading_result": {"type": "case", "max_score": 10}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event.get("event_type") == "case_grading_completed"
    assert event.get("case_stem_fallback") == "submission_text"
    assert "问题:" in seen["stem"]


@pytest.mark.asyncio
async def test_case_rubric_v1_partial_reference_scope_honest_denominator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0 兜底满分根治（2026-08-01 取证）：参考答案只覆盖 1/4 小问时，全中不得
    等于整题满分——按覆盖比例缩放点池、分母还原整题名义满分、发声 partial_scope。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])

    async def _fake_extract(reference, stem, complete_fn, api_key, *, model="deepseek-chat",
                            provider_authority=""):
        return [{"point_id": "R1", "text": "见证记录", "score": 1.0, "policy": "list",
                 "required_terms": []}]

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"R1": {"status": G.HIT}}

    monkeypatch.setattr(G, "extract_rubric_from_reference_async", _fake_extract)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)

    ctx = {
        "question_id": "", "user_answer": "我的作答内容",
        "question_stem": "【背景资料】某工程。\n问题1：A？\n问题2：B？\n问题3：C？\n问题4：D？",
        "correct_answer": "问题1的官方答案（兄弟行，只覆盖 1 问）",
        "case_reference_covered_count": 1,
        "case_stem_subquestion_count": 4,
        "construction_grading_result": {"type": "case", "max_score": 10},
    }
    event = await _grade_one_case_v1(ctx, student_id="s1", complete=None, key="k", _G=G)
    assert event["event_type"] == "case_grading_completed"
    assert event["case_grading_partial_scope"] == "1/4"
    assert event["max_score"] == 10.0, "分母必须是整题名义满分"
    assert event["awarded_score"] <= 2.51, f"1/4 覆盖全中最多得 2.5，实得 {event['awarded_score']}"
    assert event["official_score_allowed"] is False

    # 全覆盖时行为不变（不得误伤）
    ctx_full = dict(ctx, case_reference_covered_count=4, case_stem_subquestion_count=4)
    ev_full = await _grade_one_case_v1(ctx_full, student_id="s1", complete=None, key="k", _G=G)
    assert "case_grading_partial_scope" not in ev_full
    assert ev_full["awarded_score"] == ev_full["max_score"] == 10.0


@pytest.mark.asyncio
async def test_case_rubric_v1_finalizer_audit_anchor_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    """单一 finalizer 验算锚（codex 不变量审计 §2.2）：池 30 / 名义满分 20 /
    命中 25 / 覆盖 2/4 → 缩放后命中 8.33、对外 8.33/20。同时验证 capability
    层不再事后改分（分数三字段全部出自 finalize_case_score）。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])

    async def _fake_extract(reference, stem, complete_fn, api_key, *, model="deepseek-chat",
                            provider_authority=""):
        return [
            {"point_id": "R1", "text": "点一", "score": 10.0, "policy": "list", "required_terms": []},
            {"point_id": "R2", "text": "点二", "score": 10.0, "policy": "list", "required_terms": []},
            {"point_id": "R3", "text": "点三", "score": 10.0, "policy": "list", "required_terms": []},
        ]

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"R1": {"status": G.HIT}, "R2": {"status": G.HIT},
                "R3": {"status": G.PARTIAL, "partial_ratio": 0.5}}

    monkeypatch.setattr(G, "extract_rubric_from_reference_async", _fake_extract)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)

    event = await _grade_one_case_v1(
        {"question_id": "", "user_answer": "我的作答内容",
         "question_stem": "【背景资料】某工程。\n问题1：A？\n问题2：B？\n问题3：C？\n问题4：D？",
         "correct_answer": "问题1与问题2的官方答案",
         "case_reference_covered_count": 2, "case_stem_subquestion_count": 4,
         "construction_grading_result": {"type": "case", "max_score": 20}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    assert event["max_score"] == 20.0
    assert event["scoring_scope_max"] == 10.0
    assert abs(event["awarded_score"] - 8.33) <= 0.02, f"实得 {event['awarded_score']}"
    assert event["case_grading_partial_scope"] == "2/4"


@pytest.mark.asyncio
async def test_case_rubric_v1_tier1_pool_capped_at_nominal(monkeypatch: pytest.MonkeyPatch) -> None:
    """tier-1 封顶门禁（2026-08-01 裁决）：编译点池 Σ=30 > 名义满分 20 时
    **现阶段不封顶**——cg.max_score 出自 V0 文本解析不可靠（实证夹具池 3/名义 1），
    按它封顶会砍错判对的分；确定性封顶 = canonical 431 带逐点分值上服的硬前置。
    本测试钉住 observe-only 语义，防止封顶在前置未满足时被误开。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    pool = [
        {"point_id": f"C{i}", "text": f"编译点{i}", "score": 10.0, "policy": "list",
         "required_terms": []} for i in range(3)
    ]
    monkeypatch.setattr(G, "load_rubric", lambda qid: [dict(p) for p in pool] if qid == "8817" else [])

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {p["point_id"]: {"status": G.HIT} for p in points}

    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)
    event = await _grade_one_case_v1(
        {"question_id": "8817", "user_answer": "我的作答", "question_stem": "题面",
         "correct_answer": "官方答案",
         "construction_grading_result": {"type": "case", "max_score": 20}},
        student_id="s1", complete=None, key="k", _G=G,
    )
    # tier-1 现阶段刻意不封顶（cg.max_score 出自 V0 解析不可靠；确定性封顶
    # = canonical 431 带逐点分值上服的硬前置），只发 observe-only marker。
    assert event["awarded_score"] == 30.0
    assert event["max_score"] == 30.0
    assert "case_score_capped_from" not in event
    assert event["point_pool_exceeds_max"] > 0


@pytest.mark.asyncio
async def test_case_rubric_v1_stage_hook_is_observation_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """渐进吐字（L4 2026-08-01，contracts/turn.md「渐进发射不改变终态」）：判分核
    把已经算完的阶段事实报给观察者（走了哪一档 rubric、拆出几个点、第几组判完），
    但观察者**零判分权力**——挂上它与不挂它，GradingEvent 逐字段相同；观察者抛错
    也不得改变判分。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: _RUBRIC if qid == "case-9006" else [])

    async def _fake(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.HIT}, "P3": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake)

    ctx = {
        "question_id": "case-9006",
        "user_answer": "共用开关箱不妥",
        "construction_grading_result": {"type": "case", "max_score": 3},
    }
    baseline = await _grade_one_case_v1(dict(ctx), student_id="s1", complete=None, key="k", _G=G)

    seen: list[tuple[str, dict]] = []

    async def _on_stage(kind: str, **facts):
        seen.append((kind, facts))

    observed = await _grade_one_case_v1(
        dict(ctx), student_id="s1", complete=None, key="k", _G=G, on_stage=_on_stage
    )

    kinds = [kind for kind, _facts in seen]
    assert kinds[0] == "rubric_source"
    assert seen[0][1] == {"tier": "compiled", "point_count": 3}
    assert "rubric_ready" in kinds
    assert "judge_group_done" in kinds
    assert kinds[-1] == "judge_done"
    # 终态即真值：唯一允许的差异是 event_id / 时间戳类字段（此 fixture 不含）。
    assert observed == baseline

    async def _boom(_kind: str, **_facts):
        raise RuntimeError("observer down")

    resilient = await _grade_one_case_v1(
        dict(ctx), student_id="s1", complete=None, key="k", _G=G, on_stage=_boom
    )
    assert resilient == baseline


# ---------------------------------------------------------------------------
# OD-005：每小问独立抽取 + 独立封顶（整卷半答假满分歼灭）
# ---------------------------------------------------------------------------

_OD005_STEM = (
    "【背景资料】某施工企业中标新建办公楼工程，施工过程中出现若干问题。\n"
    "问题1：指出不妥之处并说明理由？\n"
    "问题2：写出正确做法？\n"
    "问题3：写出构造名称？\n"
    "问题4：补充工艺流程？"
)
# 治理组 bundle：4 个小问的官方答案各自成行（C3 终修后整组采纳 = 全覆盖）。
_OD005_SUBQ_REFERENCES = [
    {"index": str(i), "answer": f"官方答案{i}"} for i in range(1, 5)
]
_OD005_JOINED_REFERENCE = "\n".join(s["answer"] for s in _OD005_SUBQ_REFERENCES)


def _od005_install_fakes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """抽取器行为建模（live 实证形态，非臆造）：

    - **整段自由抽取**（旧路径）：拿到 4 问拼接成的一段，点位分布不保证——
      live 三轮里两轮的点全落在**已答的问 1**上，于是"只答问 1"命中即满分。
      这里用"点位跟随参考首行身份"确定性复现该形态。
    - **逐问抽取**（新路径）：每次只拿到那一问的答案，点位天然带该问身份，
      分布偏斜在结构上不可能发生。

    判分侧用确定性包含判定（学生作答里出现该点表述即命中），不接触 LLM。
    """
    calls: list[str] = []

    async def _fake_extract(reference, stem, complete_fn, api_key, *, model="deepseek-chat",
                            provider_authority=""):
        text = str(reference or "").strip()
        calls.append(text)
        tag = text.splitlines()[0].strip() if text else ""
        return [
            {"point_id": f"P{i}", "text": f"{tag}要点{i}", "score": 1.0,
             "policy": "qualitative", "required_terms": []}
            for i in range(1, 5)
        ]

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {
            str(p.get("point_id")): {
                "status": G.HIT if str(p.get("text") or "") in str(answer or "") else G.MISS
            }
            for p in points
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])
    monkeypatch.setattr(G, "extract_rubric_from_reference_async", _fake_extract)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)
    return calls


def _od005_answer(*answered_indexes: int) -> str:
    """学生作答：把这几问的全部采分点表述写全（其余问一个字没写）。"""
    return "\n".join(
        f"问题{idx}：" + "、".join(f"官方答案{idx}要点{k}" for k in range(1, 5))
        for idx in answered_indexes
    )


def _od005_ctx(answered: tuple[int, ...], **overrides: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "question_id": "",
        "user_answer": _od005_answer(*answered),
        "question_stem": _OD005_STEM,
        "user_stem": _OD005_STEM,
        "correct_answer": _OD005_JOINED_REFERENCE,
        "case_reference_subquestions": [dict(s) for s in _OD005_SUBQ_REFERENCES],
        "case_reference_covered_count": 4,
        "case_stem_subquestion_count": 4,
        "construction_grading_result": {"type": "case", "max_score": 10},
    }
    ctx.update(overrides)
    return ctx


@pytest.mark.asyncio
async def test_od005_half_answered_full_paste_cannot_reach_full_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OD-005 主证伪测（2026-08-01 live 实证：t8 形态 3 轮 2 轮 10/10）。

    整卷 4 问粘贴 + **只答问 1**，参考是治理组的 4 问全覆盖答案。旧路径把 4 问
    答案 ``"\\n".join`` 成一段做**一次**自由抽取——点位分布不保证，恰好全落在
    已答的问 1 时，全命中 + scope_ratio=1（全覆盖 → 整题封顶不介入）= 10/10。
    修法：每小问独立抽取、独立封顶（每问上限 = 名义满分 / 问数），
    没答的问点位全 miss → 该问 0 分，不需要"哪几问已答"的第二个判定权威。
    """
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    calls = _od005_install_fakes(monkeypatch)
    event = await _grade_one_case_v1(
        _od005_ctx((1,)), student_id="s1", complete=None, key="k", _G=G
    )

    assert event["event_type"] == "case_grading_completed"
    assert event["max_score"] == 10.0, "对外分母恒为整题名义满分"
    assert event["awarded_score"] <= 2.51, (
        f"只答 1/4 问最多得 2.5，实得 {event['awarded_score']}（整卷半答假满分）"
    )
    assert event["awarded_score"] >= 2.49, "答对的那一问必须足额给分，不得连坐"
    # 逐问抽取的结构证据：抽取被调用 4 次，每次只喂那一问的答案。
    assert len(calls) == 4, f"每小问应独立抽取一次，实得 {len(calls)} 次"
    assert sorted(calls) == [s["answer"] for s in _OD005_SUBQ_REFERENCES]
    # 采分点必须带 question_no（渲染 coverage 对账吃它）。
    question_nos = {str(p.get("question_no")) for p in event["scoring_points"]}
    assert question_nos == {"1", "2", "3", "4"}, f"采分点缺 question_no：{question_nos}"
    # 覆盖对账消费同一个确定性盖章：rubric 确实盖住 4 问（诚实的 4/4），
    # 分数只反映"只答了问 1"——覆盖面与得分面不再互相冒充。
    assert event["case_subq_coverage"] == "4/4"
    assert "case_subq_uncovered" not in event
    # 每问封顶表随事件出场（live 关闭判据按它分组）。
    assert event["case_per_subq_grading"] == "4/4"
    assert event["case_subq_score_caps"] == "q1:2.5,q2:2.5,q3:2.5,q4:2.5"
    # 归一化已经把每问点池压到该问名义满分，所以封顶闸在正常链路上不咬人
    # （它是第二道防线：点池构造方式若变、或走 PGO 覆盖计分时才发力，
    # 咬人的用例在 test_rubric_grader_v1.py 的 finalize 单测里）。
    assert "case_subq_score_capped" not in event
    # 一组=一问：逐组发射即"问 k 判完"。
    assert event["adjudication_strategy"] == "dynamic_parallel_subquestion_groups"
    assert event["adjudication_group_count"] == 4


@pytest.mark.asyncio
async def test_od005_full_answer_still_scores_full_marks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不得误伤：四问全答全中仍是满分（每问封顶之和 = 整题名义满分）。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    _od005_install_fakes(monkeypatch)
    event = await _grade_one_case_v1(
        _od005_ctx((1, 2, 3, 4)), student_id="s1", complete=None, key="k", _G=G
    )
    assert event["awarded_score"] == 10.0
    assert event["max_score"] == 10.0


@pytest.mark.asyncio
async def test_od005_three_tier_monotonic(monkeypatch: pytest.MonkeyPatch) -> None:
    """三档单调：答 1 问 / 2 问 / 4 问 → 2.5 / 5.0 / 10.0（每问等权封顶）。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    _od005_install_fakes(monkeypatch)
    scores = []
    for answered in ((1,), (1, 2), (1, 2, 3, 4)):
        event = await _grade_one_case_v1(
            _od005_ctx(answered), student_id="s1", complete=None, key="k", _G=G
        )
        scores.append(event["awarded_score"])
    assert scores == sorted(scores), f"三档必须单调不减，实得 {scores}"
    assert abs(scores[0] - 2.5) <= 0.02
    assert abs(scores[1] - 5.0) <= 0.02
    assert abs(scores[2] - 10.0) <= 0.02


@pytest.mark.asyncio
async def test_od005_kill_switch_off_restores_single_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kill switch 关 → 逐字回旧形状：一次整段抽取、无每问封顶。

    这条既是回滚肌肉，也是"红测在旧路径上确实红"的**同进程证据**：
    同一夹具、同一半答卷，旧路径给出 10/10。
    """
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    calls = _od005_install_fakes(monkeypatch)
    monkeypatch.setenv("LUBAN_CASE_PER_SUBQ_GRADING", "off")
    event = await _grade_one_case_v1(
        _od005_ctx((1,)), student_id="s1", complete=None, key="k", _G=G
    )
    assert len(calls) == 1, "关闸后必须回到整段一次抽取"
    assert event["awarded_score"] == 10.0, "旧路径的病灶形态（半答假满分）原样保留"
    assert "case_subq_score_caps" not in event


@pytest.mark.asyncio
async def test_od005_single_subquestion_reference_keeps_legacy_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非治理 / 单行参考路径行为不变：只有 1 个小问参考时不进逐问链，
    仍走既有 scope_ratio 整题封顶（P0 修的那条不变量）。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    calls = _od005_install_fakes(monkeypatch)
    ctx = _od005_ctx(
        (1,),
        correct_answer="官方答案1",
        case_reference_subquestions=[{"index": "1", "answer": "官方答案1"}],
        case_reference_covered_count=1,
    )
    event = await _grade_one_case_v1(ctx, student_id="s1", complete=None, key="k", _G=G)
    assert len(calls) == 1
    assert event["case_grading_partial_scope"] == "1/4"
    assert event["awarded_score"] <= 2.51


# ---------------------------------------------------------------------------
# R2（task#26 2026-08-01）：判分分母的权威阶梯（canonical > bundle > stem > 参考侧）
# ---------------------------------------------------------------------------
# 病灶：deep_question 自持案例路径（practice / 直调 capability）的 ctx **没有**
# ``case_stem_subquestion_count``——那个键只有 TutorBot 侧的 ctx 构建器
# （loop.py ``_build_v1_case_ctx``）会写。于是旧式
# ``_sub_n = max(ctx.case_stem_subquestion_count, len(参考侧))`` 恒塌成
# ``len(参考侧)``：纯参考侧计数、与题面零交叉核对。参考侧是检索装配的产物
# （C3 取全成不成、兄弟行重复、答案冲突是否被 C2 裁决都会改变它），拿它当分母
# = 让检索运气决定「这道题有几问」，参考多一项学生每一问就被稀释一份分。


# 参考侧 5 项（第 5 项是幽灵：兄弟行重复 / 跨题串入），题面只有 4 问。
_R2_PHANTOM_SUBQ_REFERENCES = [
    {"index": str(i), "answer": f"官方答案{i}"} for i in range(1, 6)
]


def _r2_self_hosted_ctx(**overrides: Any) -> dict[str, Any]:
    """自持路径 ctx 的真实形状：**没有** ``case_stem_subquestion_count``。"""
    ctx: dict[str, Any] = {
        "question_id": "",
        "user_answer": _od005_answer(1),
        "question_stem": _OD005_STEM,
        "user_stem": _OD005_STEM,
        "correct_answer": "\n".join(s["answer"] for s in _R2_PHANTOM_SUBQ_REFERENCES),
        "case_reference_subquestions": [dict(s) for s in _R2_PHANTOM_SUBQ_REFERENCES],
        "case_reference_covered_count": 5,
        "construction_grading_result": {"type": "case", "max_score": 10},
    }
    ctx.update(overrides)
    return ctx


def test_r2_denominator_prefers_stem_over_reference_side_count() -> None:
    """R2 主证伪测：**参考侧 5 项但题面 4 问 → 分母 4，不是 5**。

    旧口径 ``max(ctx.case_stem_subquestion_count, len(refs))`` 在这个 ctx 上恒等于
    ``max(0, 5) = 5``（该键自持路径不存在）——本用例的 5≠4 就是它的反例。
    """
    from deeptutor.capabilities.deep_question import _resolve_case_denominator

    ctx = _r2_self_hosted_ctx()
    assert "case_stem_subquestion_count" not in ctx, "自持路径 ctx 不带这个键（病灶前提）"

    denominator, source = _resolve_case_denominator(ctx, reference_count=5)

    assert (denominator, source) == (4, "stem"), (
        f"题面 4 问必须压过参考侧 5 项，实得 {denominator}（来源 {source}）"
    )
    # 旧口径的同进程反证：它会给出 5。
    assert max(int(ctx.get("case_stem_subquestion_count") or 0), 5) == 5


def test_r2_denominator_canonical_bank_outranks_stem_and_reference() -> None:
    """①canonical431：认出题级组时，分母出自编译期治理裁决过的题面结构。

    只读 nominal 表的结构事实（每案例几问），不读采分点内容——那份 bank 的
    ``production_authorized=false``，分值权威一分钱都不许进判分。
    """
    from deeptutor.capabilities.deep_question import _resolve_case_denominator
    from deeptutor.services.construction_grading.rubric_grader_v1 import (
        canonical_case_subquestion_counts,
    )

    counts = canonical_case_subquestion_counts()
    assert counts, "canonical431 nominal 表必须可读（阶梯①的供给前提）"
    group_id, expected = next(
        (gid, n) for gid, n in sorted(counts.items()) if n not in (0, 4)
    )

    denominator, source = _resolve_case_denominator(
        _r2_self_hosted_ctx(case_group_id=group_id), reference_count=5
    )
    assert (denominator, source) == (expected, "canonical")

    # 题级组也可以从复合 qid 认出（``{year}-case{n}::E{k}``）。
    denominator2, source2 = _resolve_case_denominator(
        _r2_self_hosted_ctx(question_id=f"{group_id}::E1"), reference_count=5
    )
    assert (denominator2, source2) == (expected, "canonical")


def test_r2_denominator_falls_to_bundle_surface_then_reference_with_marker() -> None:
    """②C3 bundle surface 计数；④全不可得才退参考侧，**并且必须发声**。"""
    from deeptutor.capabilities.deep_question import _resolve_case_denominator

    bundle_ctx = _r2_self_hosted_ctx(
        question_stem="", user_stem="", stem="",
        case_bundle={
            "covered_subquestions": [
                {"display_index": str(i), "stem": f"【问题】{i}. …"} for i in range(1, 4)
            ]
        },
    )
    assert _resolve_case_denominator(bundle_ctx, reference_count=5) == (3, "bundle")

    # 题面/组/bundle 全不可得 —— 分母只能数参考侧，这是降级，必须带 marker。
    blind_ctx = _r2_self_hosted_ctx(question_stem="", user_stem="", stem="")
    assert _resolve_case_denominator(blind_ctx, reference_count=5) == (
        5, "reference_fallback",
    )


@pytest.mark.asyncio
async def test_r2_phantom_reference_row_does_not_dilute_each_subquestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """端到端：幽灵参考行不得稀释每一问的上限，且分母来源上事件。

    同一份「只答问 1」的作答：题面 4 问 → 问 1 上限 10/4 = 2.5。旧口径分母 5 →
    上限 10/5 = 2.0，学生凭空少 0.5 分，而且**看不出为什么**（无 marker）。
    """
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    _od005_install_fakes(monkeypatch)
    event = await _grade_one_case_v1(
        _r2_self_hosted_ctx(), student_id="s1", complete=None, key="k", _G=G
    )

    assert event["event_type"] == "case_grading_completed"
    assert event["case_denominator_source"] == "stem"
    assert event["case_per_subq_grading"].endswith("/4"), (
        f"分母必须是题面的 4，实得 {event['case_per_subq_grading']}"
    )
    assert abs(event["awarded_score"] - 2.5) <= 0.02, (
        f"答对的那一问按 10/4 足额给分，实得 {event['awarded_score']}（旧口径会给 2.0）"
    )
    assert event["max_score"] == 10.0, "对外分母恒为整题名义满分"


def test_r2_denominator_source_marker_is_registered_on_the_export_whitelist() -> None:
    """marker 必须进 CASE_GRADING_AUTHORITY_EXPORT_KEYS —— 漏一张名单 = 该 sink 永久 0 命中。"""
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_GRADING_AUTHORITY_EXPORT_KEYS,
        CASE_GRADING_TURN_METADATA_KEYS,
    )

    assert "case_denominator_source" in CASE_GRADING_AUTHORITY_EXPORT_KEYS
    assert "case_denominator_source" in CASE_GRADING_TURN_METADATA_KEYS


def test_r2_canonical_denominator_reader_never_touches_scoring_content() -> None:
    """治理边界：读分母不得让未授权 bank 变成判分权威。

    - ``canonical_case_subquestion_counts`` 只吐 ``{case_group_id: 小问数}`` 整数；
    - 在服判分 bank 仍是 legacy/authorized（登记 canonical431 slot 没有把它上服）。
    """
    from deeptutor.services.construction_grading import rubric_grader_v1 as _G2

    counts = _G2.canonical_case_subquestion_counts()
    assert counts and all(
        isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in counts.items()
    ), "分母表只许是 {case_group_id: 小问数}"

    _G2._rubric_bank()
    identity = _G2.active_bank_identity()
    assert identity["slot"] == "legacy" and identity["governance"] == "authorized", (
        f"在服判分 bank 必须仍是授权的 legacy，实得 {identity}"
    )

    # 治理闸仍拦得住把 canonical431 当判分 bank 装载（默认要求生产授权）。
    bank, reason = _G2._load_bank_slot("canonical431")
    assert bank is None and reason == "unauthorized"


# ---------------------------------------------------------------------------
# OD-005 补刀：每问的**题面**也必须是自己那一问（live 22:09 轮取证）
# ---------------------------------------------------------------------------

# 生产形态：ctx["question_stem"] 来自 eq.stem = **bank 行**题面（背景 + 只有问 1）。
_OD005B_BANK_ROW_STEM = (
    "【背景资料】某施工企业中标新建一办公楼工程，地下二层，地上二十八层。\n"
    "【问题】1. 指出工程质量计划编制和管理中的不妥之处，并写出正确做法。"
)
# 各 bundle 行自带的 surface = 共享背景 + 它自己那一问（真正的每问题面权威）。
_OD005B_ITEM_STEMS = {
    "1": _OD005B_BANK_ROW_STEM,
    "2": "【背景资料】某施工企业中标新建一办公楼工程。\n【问题】2. 灌注桩桩身完整性检测方法还有哪些？",
    "3": "【背景资料】某施工企业中标新建一办公楼工程。\n【问题】3. 指出钢筋接头面积百分率要求中的不妥之处。",
    "4": "【背景资料】某施工企业中标新建一办公楼工程。\n【问题】4. 写出屋面卷材流淌原因分析中的不妥项。",
}


def _od005b_install_fakes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """抽取器行为建模（live 22:09 轮实证形态）：**题面压过参考答案**。

    生产实证：给问 2 喂「问 2 的参考答案 + 问 1 的题面」，抽出来的 6 个点全是
    问 1 的内容（"质量计划应动态管理""质量控制点关键部位"），池 2.5 分。
    所以这里让假抽取器的点位**跟随题面里的问号**——题面给错，点就串问。
    """
    stems_seen: list[str] = []

    async def _fake_extract(reference, stem, complete_fn, api_key, *, model="deepseek-chat",
                            provider_authority=""):
        stems_seen.append(str(stem or ""))
        match = re.search(r"【问题】\s*([0-9]+)", str(stem or ""))
        tag = match.group(1) if match else "0"   # 无题面 → 只能凭参考答案
        if tag == "0":
            tag = (str(reference or "").strip() or "?")[:6]
        return [
            {"point_id": f"P{i}", "text": f"问{tag}要点{i}", "score": 1.0,
             "policy": "qualitative", "required_terms": []}
            for i in range(1, 5)
        ]

    async def _fake_judge(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {
            str(p.get("point_id")): {
                "status": G.HIT if str(p.get("text") or "") in str(answer or "") else G.MISS
            }
            for p in points
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda qid: [])
    monkeypatch.setattr(G, "extract_rubric_from_reference_async", _fake_extract)
    monkeypatch.setattr(G, "batch_judge_async", _fake_judge)
    return stems_seen


@pytest.mark.asyncio
async def test_od005b_bank_row_stem_must_not_leak_into_sibling_subquestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OD-005 补刀主证伪测（live SHA 6a730b41 实证：t8 半答 3 轮 5.65/5.16/5.65）。

    逐问抽取与逐问封顶都正确工作了（marker 全在、一组一问、q1 得 2.50/2.50），
    但问 2/3/4 的点池里装的是**问 1 的采分点**——因为它们的抽取拿到的是问 1 的
    题面（``ctx["question_stem"]`` = bank 行题面，只含问 1；旧版切不出时 fail-open
    顶替）。学生逐字抄问 1 的答案于是在 q2/q3/q4 上又拿了 3.15 分。

    修法：每问用**自己那一问的题面**（bundle 行自带 surface）；切不出时宁可不给
    题面，也绝不顶替兄弟问的题面。
    """
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    stems_seen = _od005b_install_fakes(monkeypatch)
    # 学生只答问 1：逐字写全问 1 的采分点表述。
    answer = "问题1：" + "、".join(f"问1要点{k}" for k in range(1, 5))
    ctx = {
        "question_id": "17371",
        "user_answer": answer,
        # 生产实况：question_stem = bank 行题面（只含问 1），user_stem = 学生整卷
        "question_stem": _OD005B_BANK_ROW_STEM,
        "user_stem": (
            "【背景资料】某施工企业中标新建一办公楼工程。\n"
            "【问题】\n1. 指出工程质量计划编制和管理中的不妥之处。\n"
            "2. 灌注桩桩身完整性检测方法还有哪些？\n"
            "3. 指出钢筋接头面积百分率要求中的不妥之处。\n"
            "4. 写出屋面卷材流淌原因分析中的不妥项。"
        ),
        "correct_answer": "\n".join(f"官方答案{i}" for i in range(1, 5)),
        "case_reference_subquestions": [
            {"index": str(i), "answer": f"官方答案{i}", "stem": _OD005B_ITEM_STEMS[str(i)]}
            for i in range(1, 5)
        ],
        "case_reference_covered_count": 4,
        "case_stem_subquestion_count": 4,
        "construction_grading_result": {"type": "case", "max_score": 10},
    }
    event = await _grade_one_case_v1(ctx, student_id="s1", complete=None, key="k", _G=G)

    # 每问的抽取必须拿到**自己那一问**的题面，一次都不许拿到兄弟问的。
    assert len(stems_seen) == 4
    seen_tags = sorted(re.search(r"【问题】\s*([0-9]+)", s).group(1) for s in stems_seen)
    assert seen_tags == ["1", "2", "3", "4"], f"题面串问了：{seen_tags}"

    # 点位不得串问：q2/q3/q4 的池里不许出现问 1 的采分点。
    for point in event["scoring_points"]:
        q = str(point.get("question_no"))
        text = str(point.get("knowledge_point") or "")
        assert text.startswith(f"问{q}要点"), f"q{q} 的池里混进了 {text!r}"

    # 只答 1/4 问 → 总分 ≈ 2.5，绝不是 live 观测到的 5.65。
    assert event["awarded_score"] <= 2.51, (
        f"只答 1/4 问最多 2.5，实得 {event['awarded_score']}（串问采分点泄分）"
    )
    assert event["awarded_score"] >= 2.49
    assert event["case_per_subq_grading"] == "4/4"


@pytest.mark.asyncio
async def test_od005b_missing_own_stem_falls_back_to_slicing_then_to_no_stem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """题面权威阶梯：①行自带 surface ②切学生整卷 ③不给题面。
    第③档下抽取只凭参考答案 —— 仍然不许顶替兄弟问的题面。"""
    from deeptutor.capabilities.deep_question import _grade_one_case_v1

    stems_seen = _od005b_install_fakes(monkeypatch)
    answer = "问题1：" + "、".join(f"问1要点{k}" for k in range(1, 5))
    ctx = {
        "question_id": "17371",
        "user_answer": answer,
        "question_stem": _OD005B_BANK_ROW_STEM,   # 只含问 1
        "user_stem": "",                          # 连整卷题面也没有 → 只能退到第③档
        "correct_answer": "\n".join(f"官方答案{i}" for i in range(1, 5)),
        "case_reference_subquestions": [
            {"index": str(i), "answer": f"官方答案{i}", "stem": ""} for i in range(1, 5)
        ],
        "case_reference_covered_count": 4,
        "case_stem_subquestion_count": 4,
        "construction_grading_result": {"type": "case", "max_score": 10},
    }
    event = await _grade_one_case_v1(ctx, student_id="s1", complete=None, key="k", _G=G)
    # 问 1 可以从 question_stem 里**正当地**切出自己那一问（它本来就只含问 1）；
    # 问 2/3/4 切不出 → 必须留空，绝不顶替成问 1 的题面。
    assert "指出工程质量计划编制和管理中的不妥之处" in stems_seen[0], "问 1 应切出自己那一问"
    assert stems_seen[1:] == ["", "", ""], (
        f"退化档不得顶替兄弟问题面：{[x[:30] for x in stems_seen[1:]]}"
    )
    assert event["awarded_score"] <= 2.51
