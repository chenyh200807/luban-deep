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


class _FakeEvent:
    event_id = "evt_v1_case_1"


class _FakeLearnerStateService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def append_memory_event(self, user_id: str, **kwargs):
        self.calls.append({"user_id": user_id, **kwargs})
        return _FakeEvent()


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
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")  # explicit on (default is also on)
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
async def test_v1_case_render_default_on_for_non_qa_user(monkeypatch: pytest.MonkeyPatch) -> None:
    # DEFAULT ON (full rollout, no cohort): a real (non-qa) user with NO env flag set still gets V1.
    monkeypatch.delenv("LUBAN_CASE_RUBRIC_V1_ENABLED", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {"point_id": "P1", "text": "共用一个开关箱不妥", "score": 1.0, "policy": "boolean_judgment",
         "required_terms": []}])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {"P1": {"status": G.HIT}}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    md = _case_md()
    md["user_id"] = "real_user_123"               # not qa_/test_ -> still graded (no cohort gate anymore)
    render = await _loop()._v1_case_render(runtime_metadata=md, user_message="共用一个开关箱不妥")
    assert "逐采分点点评" in render


@pytest.mark.asyncio
async def test_v1_case_render_degraded_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    # FAIL-SAFE: batch LLM yields no trustworthy verdict (empty) -> V1 returns no render so the turn
    # falls back to legacy, AND the _v1_case_graded marker is NOT set (legacy demote stays in control).
    monkeypatch.delenv("LUBAN_CASE_RUBRIC_V1_ENABLED", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {"point_id": "P1", "text": "点1", "score": 1.0, "policy": "list", "required_terms": []}])

    async def _empty(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {}

    monkeypatch.setattr(G, "batch_judge_async", _empty)
    md = _case_md()
    render = await _loop()._v1_case_render(runtime_metadata=md, user_message="作答")
    assert render == ""                              # V1 did NOT surface a 0/满分 grade
    assert not md.get("_v1_case_graded")             # legacy demote remains in control


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
    md = _case_md()
    out = await _loop()._apply_v1_or_case_fallback(
        "智能体自由答复：你写得不错，继续保持。", runtime_metadata=md, user_message="点1")
    assert "逐采分点点评" in out                                      # V1 took over (not the agent text)
    assert md.get("_v1_case_graded") is True


@pytest.mark.asyncio
async def test_apply_v1_or_case_fallback_no_scene_no_authority_does_not_invent_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This mirrors the 2026-06-08 production trace failure shape: TutorBot produced
    # teaching feedback, but the turn carried no case_grading scene or exact-question
    # authority. The loop must not fabricate a score from that shape.
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no authority")))
    md = {
        "question_lifecycle_scene": None,
        "_prefetched_exact_question": None,
        "active_object": None,
        "construction_grading_result": None,
    }
    out = await _loop()._apply_v1_or_case_fallback(
        "你这个答案方向上有可取之处，但还需要补充关键采分点。",
        runtime_metadata=md,
        user_message="帮我批改这道案例题",
    )
    assert out == ""


@pytest.mark.asyncio
async def test_v1_case_render_writes_grading_to_brain_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {
            "point_id": "P1",
            "text": "应编制临时用电施工组织设计",
            "score": 1.0,
            "policy": "exact_required",
            "required_terms": ["临时用电施工组织设计"],
        }
    ])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {
            "P1": {
                "status": G.MISS,
                "mistake_type": "near_synonym_not_exact",
                "evidence_span": "普通施工方案",
            }
        }

    fake_service = _FakeLearnerStateService()
    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: fake_service,
    )

    md = _case_md()
    md["turn_id"] = "turn_v1_case"
    md["bot_id"] = "construction-exam-coach"
    out = await _loop()._apply_v1_or_case_fallback(
        "智能体自由答复：我先不打分。", runtime_metadata=md, user_message="普通施工方案")

    assert "逐采分点点评" in out
    assert len(fake_service.calls) == 1
    call = fake_service.calls[0]
    assert call["user_id"] == "qa_loop_v1"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "case_grading_completed"
    assert md["grading_to_brain_loop"]["writeback_count"] == 1
    assert md["learning_evidence_event_id"] == "evt_v1_case_1"
    assert md["learning_training_intent"]["source"] == "grading_to_brain_loop"
    assert md["personalization_context"]["source"] == "PersonalizationContextPack"
    assert md["next_best_action"]["source"] == "training_intent"
