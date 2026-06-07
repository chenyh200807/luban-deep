"""TutorBot loop V1 case-grading integration (`_v1_case_render` / `_build_v1_case_ctx` /
`_apply_v1_or_case_fallback`).

Hermetic: rubric_grader_v1.load_rubric + batch_judge_async stubbed (no LLM). Proves V1 takes over the
TutorBot case-grading turn when score authority + flag are present (becoming the score authority),
extracts the case reference from covered_subquestions[].authoritative_answer, and stays inert otherwise
(non-case scene / no authority / flag off) so non-grading turns are byte-identical.
"""
from __future__ import annotations

import asyncio

import pytest

from deeptutor.services.construction_grading import rubric_grader_v1 as G
from deeptutor.tutorbot.agent.loop import AgentLoop


def _loop() -> AgentLoop:
    # V1 methods only use static helpers — no full construction needed.
    return AgentLoop.__new__(AgentLoop)


def _case_md() -> dict:
    return {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "question_id": "CASE-1",
            "stem": "指出事件二中临时用电管理的不妥之处。",
            "covered_subquestions": [
                {"authoritative_answer": "共用一个开关箱不妥，应采用专用开关箱"},
                {"authoritative_answer": "应编制临时用电施工组织设计"},
            ],
        },
    }


def test_build_v1_case_ctx_extracts_reference_from_covered_subquestions() -> None:
    ctx = AgentLoop._build_v1_case_ctx(_case_md(), "我的作答：共用一个开关箱不妥")
    assert ctx["question_id"] == "CASE-1"
    assert ctx["construction_grading_result"]["type"] == "case"
    # reference comes from covered_subquestions[].authoritative_answer (NOT top-level correct_answer)
    assert "共用一个开关箱" in ctx["correct_answer"]
    assert "应编制临时用电施工组织设计" in ctx["correct_answer"]
    assert ctx["user_answer"].startswith("我的作答")


@pytest.mark.asyncio
async def test_v1_case_render_grades_when_authority_and_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")  # global on, bypass cohort
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {"point_id": "P1", "text": "共用一个开关箱不妥", "score": 1.0, "policy": "boolean_judgment",
         "required_terms": []},
        {"point_id": "P2", "text": "应编制临时用电施工组织设计", "score": 1.0, "policy": "list",
         "required_terms": []},
    ])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}, "P2": {"status": G.MISS}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    render = await _loop()._v1_case_render(runtime_metadata=_case_md(), user_message="共用一个开关箱不妥")
    assert "逐采分点点评" in render and "【得分】" in render          # V1 render, not the agent's free text
    assert "应编制临时用电施工组织设计" in render                      # the missed point surfaced


@pytest.mark.asyncio
async def test_v1_case_render_skips_non_case_grading_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    md = _case_md()
    md["question_lifecycle_scene"] = "study_assistant"   # teaching turn, not grading
    assert await _loop()._v1_case_render(runtime_metadata=md, user_message="x") == ""


@pytest.mark.asyncio
async def test_v1_case_render_skips_when_no_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    md = {"question_lifecycle_scene": "case_grading", "user_id": "qa_x"}  # no reference -> no authority
    assert await _loop()._v1_case_render(runtime_metadata=md, user_message="x") == ""


@pytest.mark.asyncio
async def test_v1_case_render_skips_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "false")  # kill switch
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no run")))
    assert await _loop()._v1_case_render(runtime_metadata=_case_md(), user_message="x") == ""


@pytest.mark.asyncio
async def test_v1_case_render_skips_non_cohort_when_not_global(monkeypatch: pytest.MonkeyPatch) -> None:
    # per-turn flag on, but global OFF and student not in qa_/test_ cohort -> V1 must not fire
    monkeypatch.delenv("LUBAN_CASE_RUBRIC_V1_ENABLED", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no run")))
    md = _case_md()
    md["user_id"] = "real_user_123"               # not qa_/test_
    md["grading_engine_case_rubric_v1"] = True     # per-turn flag on
    assert await _loop()._v1_case_render(runtime_metadata=md, user_message="x") == ""


def test_no_authority_fallback_respects_v1_graded_marker() -> None:
    # defensive guard: once V1 graded, the legacy demote must never override it
    md = {"question_lifecycle_scene": "case_grading", "_v1_case_graded": True}
    assert AgentLoop._case_grading_no_authority_score_fallback(
        "得分：3分（满分5分），采分点1命中…", runtime_metadata=md, user_message="x") == ""


@pytest.mark.asyncio
async def test_apply_v1_or_case_fallback_falls_back_to_legacy_when_v1_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # V1 off (kill switch) -> _apply_v1_or_case_fallback must defer to the legacy demote path
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "false")
    md = {"question_lifecycle_scene": "case_grading"}  # no authority -> legacy demote applies
    out = await _loop()._apply_v1_or_case_fallback(
        "得分：3分（满分5分）", runtime_metadata=md, user_message="判断题作答")
    assert "逐采分点点评" not in out                  # not V1
    assert out == "" or "不硬估" in out                # legacy demote (or no-op)


@pytest.mark.asyncio
async def test_apply_v1_or_case_fallback_prefers_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {"point_id": "P1", "text": "点1", "score": 1.0, "policy": "list", "required_terms": []}])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    out = await _loop()._apply_v1_or_case_fallback(
        "智能体自由打分：3分", runtime_metadata=_case_md(), user_message="点1")
    assert "逐采分点点评" in out                                      # V1 took over (not the agent text)
