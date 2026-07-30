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
