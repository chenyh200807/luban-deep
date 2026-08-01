"""Single-authority regression for deep_question full-submission grading decisions.

deep_question.py:3870-3872 documents the invariant: a learner who pastes a
self-contained MCQ/case (own stem + own option order) and answers it owns the
LEARNER-SURFACE authority, so that paste-parsed turn MUST beat stale lifecycle
labels and the broader case full-submission fallback.

The bug (before the fix): the full-submission grading paths built the grading
``turn_semantic_decision`` as ``turn_semantic_decision or build_turn_semantic_decision(...)``.
When the orchestrator already supplied a router decision (the common case), the
STALE router decision won — its ``allowed_patch`` and ``target_object_ref`` are
keyed off the prior ACTIVE OBJECT, not the freshly pasted submission. When the
active object is a multi-question set (``allowed_patch=["append_answer_slots"]``)
but the learner pastes a single self-contained MCQ, the grading decision carries
``append_answer_slots`` against a single pasted answer slot — a patch-authority /
answer-slot mismatch that mis-grades.

These tests assert that the grading decision passed to ``_emit_grading_result``
(and written to ``context.metadata["turn_semantic_decision"]``) is the
PASTE-PARSED decision, not the stale router one — i.e. deep_question is the single
authority for full-submission grading decisions, matching its own comment.

Hard scope: only the full-submission grading paths (pasted self-contained MCQ /
case). Ordinary grading turns (answering the active question, no paste parse)
still defer to the router decision — covered by the no-regression tests below.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.semantic_router import build_active_object_from_question_context


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


def _capture_grading_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )
    captured: dict[str, Any] = {}

    async def capture_grading(self, **kwargs: Any) -> None:
        captured.update(kwargs)
        await kwargs["stream"].result(
            {"response": "graded"},
            source="deep_question",
            metadata={"mode": "grading"},
        )

    monkeypatch.setattr(DeepQuestionCapability, "_emit_grading_result", capture_grading)
    return captured


def _stale_multi_question_set_active_object() -> dict[str, Any]:
    """A prior ACTIVE OBJECT that is a multi-question set: the router keys
    ``append_answer_slots`` off this object's items, NOT off the pasted single MCQ."""

    set_context = {
        "question_id": "q_set_old",
        "question": "练习题组（共3题）",
        "question_type": "choice",
        "items": [
            {"question_id": "q1", "question": "第1题", "question_type": "choice",
             "options": {"A": "甲", "B": "乙"}},
            {"question_id": "q2", "question": "第2题", "question_type": "choice",
             "options": {"A": "丙", "B": "丁"}},
            {"question_id": "q3", "question": "第3题", "question_type": "choice",
             "options": {"A": "戊", "B": "己"}},
        ],
    }
    return build_active_object_from_question_context(set_context)


# --------------------------------------------------------------------------- #
# RED: the bug — stale router decision (keyed off the multi-question active set)
# must NOT win over the paste-parsed single-MCQ grading decision.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pasted_single_mcq_grading_decision_beats_stale_set_router_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_grading_monkeypatch(monkeypatch)

    stale_active_object = _stale_multi_question_set_active_object()
    # The learner pastes a fresh, self-contained SINGLE MCQ and answers it.
    message = (
        "请判这道我粘贴的单选题：题目：关于混凝土施工缝留置，下列说法正确的是？"
        "A. 施工缝可随意留置 "
        "B. 施工缝宜留在结构受剪力较大处 "
        "C. 施工缝处理时无需清除浮浆 "
        "D. 施工缝位置应按设计要求和施工技术方案确定。"
        "我的答案：D。标准答案：D。"
    )
    context = UnifiedContext(
        session_id="s-paste-single-over-stale-set",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-paste-single-over-stale-set",
            "raw_user_message": message,
            "question_lifecycle_scene": "mcq_grading",
            "active_object": stale_active_object,
            # Router decision keyed off the STALE multi-question set:
            # append_answer_slots (3 items) + target points at the old set.
            "turn_semantic_decision": {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
                "allowed_patch": ["append_answer_slots"],
                "confidence": 0.95,
                "reason": "router: answer the active question set",
                "target_object_ref": {
                    "object_type": "question_set",
                    "object_id": "q_set_old",
                },
            },
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    decision = captured["turn_semantic_decision"]
    # The pasted single MCQ owns its own learner-surface authority: the grading
    # decision must be paste-parsed (single answer slot), NOT the stale set's
    # multi-slot append patch.
    assert decision["allowed_patch"] == ["update_answer_slot"], (
        "stale multi-question-set router decision leaked into single-MCQ grading "
        f"(got allowed_patch={decision['allowed_patch']!r})"
    )
    # And the target must point at the pasted object, not the stale set.
    assert decision["target_object_ref"]["object_id"] != "q_set_old", (
        "grading decision still targets the stale active set instead of the paste"
    )
    # metadata write mirrors the same single-authority decision.
    assert context.metadata["turn_semantic_decision"]["allowed_patch"] == ["update_answer_slot"]
    assert captured["authority_source"] == "mcq_grading_full_submission"


@pytest.mark.asyncio
async def test_pasted_single_case_grading_decision_beats_stale_set_router_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_grading_monkeypatch(monkeypatch)

    stale_active_object = _stale_multi_question_set_active_object()
    message = (
        "请按案例题给我采分点评：题目：某工程基坑开挖深度8m采用排桩加内支撑支护"
        "请指出支护方案需要论证的内容。我的答案：应进行专家论证编制专项施工方案并经审批。"
        "标准答案：危大工程需组织专家论证。"
    )
    context = UnifiedContext(
        session_id="s-paste-case-over-stale-set",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-paste-case-over-stale-set",
            "raw_user_message": message,
            "question_lifecycle_scene": "case_grading",
            "active_object": stale_active_object,
            "turn_semantic_decision": {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
                "allowed_patch": ["append_answer_slots"],
                "confidence": 0.95,
                "reason": "router: answer the active question set",
                "target_object_ref": {
                    "object_type": "question_set",
                    "object_id": "q_set_old",
                },
            },
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    decision = captured["turn_semantic_decision"]
    assert decision["allowed_patch"] == ["update_answer_slot"], (
        "stale set router decision leaked into single-case grading "
        f"(got allowed_patch={decision['allowed_patch']!r})"
    )
    assert decision["target_object_ref"]["object_id"] != "q_set_old"
    assert captured["authority_source"] == "case_grading_full_submission"


# --------------------------------------------------------------------------- #
# RED→GREEN: field-level merge. The router (which sees conversation context)
# owns the INTENT facet (relation_to_active_object / next_action). The paste owns
# the SLOT-BINDING facet (allowed_patch / active_object). The whole-replacement
# fix dropped the router intent: a no-keyword revision ("不对应该是B") that the
# router classified as ``revise_answer_on_active_object`` got DOWNGRADED to
# ``answer_active_object`` by the 4-keyword heuristic. Field-level merge must
# preserve the router relation while still overriding the slot-binding from paste.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pasted_mcq_grading_preserves_router_revise_relation_without_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_grading_monkeypatch(monkeypatch)

    stale_active_object = _stale_multi_question_set_active_object()
    # A self-contained pasted MCQ whose answer is a REVISION expressed WITHOUT any
    # of the 4 keywords (改/更正/修正/订正). The router — which has conversation
    # context — already classified this as a revision.
    message = (
        "不对，应该是B：题目：关于混凝土施工缝留置，下列说法正确的是？"
        "A. 施工缝可随意留置 "
        "B. 施工缝位置应按设计要求和施工技术方案确定 "
        "C. 施工缝处理时无需清除浮浆 "
        "D. 施工缝宜留在结构受剪力较大处。"
        "我的答案：B。标准答案：B。"
    )
    router_decision = {
        # Router intent (from conversation context): this is a REVISION.
        "relation_to_active_object": "revise_answer_on_active_object",
        "next_action": "route_to_grading",
        "allowed_patch": ["append_answer_slots"],  # stale: keyed off the set
        "confidence": 0.92,
        "reason": "router: learner revises a prior answer (no keyword)",
        "target_object_ref": {
            "object_type": "question_set",
            "object_id": "q_set_old",
        },
    }
    context = UnifiedContext(
        session_id="s-paste-revise-no-keyword",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-paste-revise-no-keyword",
            "raw_user_message": message,
            "question_lifecycle_scene": "mcq_grading",
            "active_object": stale_active_object,
            "turn_semantic_decision": dict(router_decision),
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    decision = captured["turn_semantic_decision"]
    # INTENT facet preserved from router (NOT downgraded by the keyword heuristic).
    assert decision["relation_to_active_object"] == "revise_answer_on_active_object", (
        "router intent (revise) was lost — keyword heuristic downgraded it to "
        f"{decision['relation_to_active_object']!r} (whole-replacement bug)"
    )
    # SLOT-BINDING facet still overridden from the paste (single answer slot).
    assert decision["allowed_patch"] == ["update_answer_slot"], (
        "paste slot-binding must still win over the stale set's append patch "
        f"(got allowed_patch={decision['allowed_patch']!r})"
    )
    assert decision["target_object_ref"]["object_id"] != "q_set_old"
    assert captured["authority_source"] == "mcq_grading_full_submission"


# --------------------------------------------------------------------------- #
# SLOT-BINDING CONSISTENCY: the merge must not let a STALE active-object binding
# leak into the grading decision. The slot binding inside the decision dict is the
# ``target_object_ref`` (derived from the active object); the active object itself
# lives in ``context.metadata["active_object"]``. After the merge, the decision's
# target_object_ref and the metadata active_object must both describe the FRESH
# pasted object, not the stale router one — they must be self-consistent.
#
# (GLM-5.2 BLOCKER follow-up: the concern was that ``{**turn_semantic_decision}``
# spreads a stale ``active_object`` back into the decision dict while metadata is
# written fresh, leaving the two contradictory. Empirically the decision dict that
# reaches the merge is the normalized router decision, which carries NO
# ``active_object`` key — ``normalize_turn_semantic_decision`` strips it (see
# semantic_router.normalize_turn_semantic_decision). This test pins that invariant:
# even when the raw router decision is polluted with a stale ``active_object`` key,
# the merged decision must NOT carry a stale active object, and the per-decision
# slot binding (target_object_ref) must agree with the fresh metadata active object.)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pasted_single_mcq_merge_keeps_active_object_binding_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_grading_monkeypatch(monkeypatch)

    stale_active_object = _stale_multi_question_set_active_object()
    message = (
        "请判这道我粘贴的单选题：题目：关于混凝土施工缝留置，下列说法正确的是？"
        "A. 施工缝可随意留置 "
        "B. 施工缝宜留在结构受剪力较大处 "
        "C. 施工缝处理时无需清除浮浆 "
        "D. 施工缝位置应按设计要求和施工技术方案确定。"
        "我的答案：D。标准答案：D。"
    )
    # Maliciously pollute the RAW router decision with a stale active_object key
    # AND a stale target binding. The merge must not let either reach the grading
    # decision as the authoritative slot binding.
    polluted_router_decision = {
        "relation_to_active_object": "answer_active_object",
        "next_action": "route_to_grading",
        "allowed_patch": ["append_answer_slots"],
        "confidence": 0.95,
        "reason": "router: answer the active question set",
        "target_object_ref": {
            "object_type": "question_set",
            "object_id": "q_set_old",
        },
        # stale binding the spread must NOT propagate as authoritative:
        "active_object": stale_active_object,
    }
    context = UnifiedContext(
        session_id="s-paste-single-binding-consistency",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-paste-single-binding-consistency",
            "raw_user_message": message,
            "question_lifecycle_scene": "mcq_grading",
            "active_object": stale_active_object,
            "turn_semantic_decision": dict(polluted_router_decision),
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    decision = captured["turn_semantic_decision"]
    fresh_active_object = context.metadata["active_object"]

    # The metadata active_object is the FRESH pasted object, not the stale set.
    assert fresh_active_object.get("object_id") != stale_active_object.get("object_id"), (
        "metadata active_object should be the freshly pasted object, not the stale set"
    )

    # The decision's per-decision slot binding (target_object_ref) must agree with
    # the fresh metadata active object — NOT the stale set. They are self-consistent.
    fresh_target_ref = {
        "object_type": str(fresh_active_object.get("object_type") or ""),
        "object_id": str(fresh_active_object.get("object_id") or ""),
    }
    assert decision["target_object_ref"]["object_id"] == fresh_target_ref["object_id"], (
        "decision slot binding (target_object_ref) disagrees with the fresh metadata "
        f"active object: decision={decision['target_object_ref']!r} "
        f"metadata_active={fresh_target_ref!r}"
    )
    assert decision["target_object_ref"]["object_id"] != "q_set_old"

    # The decision dict must NOT carry a stale active_object binding. (Either there
    # is no active_object key at all — the canonical normalized shape — or, if a
    # future merge ever adds one, it must be the fresh object, never the stale set.)
    if "active_object" in decision:
        assert decision["active_object"].get("object_id") != stale_active_object.get("object_id"), (
            "stale router active_object leaked into the grading decision via the spread"
        )
        assert decision["active_object"].get("object_id") == fresh_active_object.get("object_id")

    assert captured["authority_source"] == "mcq_grading_full_submission"


# --------------------------------------------------------------------------- #
# NO-REGRESSION: an ordinary grading turn (answering the ACTIVE question, no
# paste-parse) is NOT a full-submission path. The router decision still governs.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ordinary_active_question_grading_still_defers_to_router_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_grading_monkeypatch(monkeypatch)

    active_context = {
        "question_id": "q_active",
        "question": "以下关于施工缝留置位置的说法，错误的是（ ）。",
        "question_type": "choice",
        "options": {
            "A": "柱的施工缝宜留置在基础、楼板、梁的顶面",
            "B": "楼梯梯段施工缝留设在梯段板跨度中部1/3范围内",
            "C": "单向板施工缝留设在跨度方向平行的任何位置",
            "D": "墙的施工缝宜留置在门洞口过梁跨中1/3范围内",
        },
        "correct_answer": "C",
    }
    active_object = build_active_object_from_question_context(active_context)
    # The learner just answers the active question with a bare letter — NOT a
    # self-contained paste (no own stem + option surface).
    message = "我选A"
    router_decision = {
        "relation_to_active_object": "answer_active_object",
        "next_action": "route_to_grading",
        "allowed_patch": ["update_answer_slot"],
        "confidence": 0.9,
        "reason": "router: answer the active question",
        "target_object_ref": {
            "object_type": "single_question",
            "object_id": "q_active",
        },
    }
    context = UnifiedContext(
        session_id="s-ordinary-active-grading",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-ordinary-active-grading",
            "raw_user_message": message,
            "question_lifecycle_scene": "mcq_grading",
            "active_object": active_object,
            "question_followup_context": active_context,
            "turn_semantic_decision": dict(router_decision),
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(context, bus))

    # Ordinary grading turn: NOT full-submission. The router decision governs and
    # is unchanged (target still the active single question, not rebuilt).
    decision = captured.get("turn_semantic_decision")
    assert decision is not None
    assert decision["target_object_ref"]["object_id"] == "q_active", (
        "ordinary grading turn must keep deferring to the router decision; the "
        "full-submission single-authority change must not touch it"
    )
    assert captured["authority_source"] != "mcq_grading_full_submission"
    assert captured["authority_source"] != "case_grading_full_submission"


# ---------------------------------------------------------------------------
# KB 溯源 tier-3 fail-open（2026-07-29 升级核心用例）
# ---------------------------------------------------------------------------
def test_fetch_stem_kb_evidence_fail_open_on_error(monkeypatch):
    """检索异常/超时/零命中一律返 []——检索绝不拖死刚复活的判分通道。"""
    import asyncio
    from deeptutor.capabilities import deep_question as dq

    async def _boom(*a, **k):
        raise RuntimeError("rag down")

    monkeypatch.setattr(dq, "rag_search", _boom)
    assert asyncio.run(dq._fetch_stem_kb_evidence("某案例题干", "construction-exam")) == []
    # kb_name 缺失直接空（不触检索）
    assert asyncio.run(dq._fetch_stem_kb_evidence("题干", None)) == []


def test_fetch_stem_kb_evidence_prefers_textbook_sources(monkeypatch):
    import asyncio
    from deeptutor.capabilities import deep_question as dq

    async def _fake(*a, **k):
        return {"evidence_bundle": {"sources": [
            {"chunk_id": "L1", "source_type": "lecture", "title": "讲义", "content": "讲义内容"},
            {"chunk_id": "T1", "source_type": "textbook", "title": "教材", "content": "教材内容"},
        ]}}

    monkeypatch.setattr(dq, "rag_search", _fake)
    out = asyncio.run(dq._fetch_stem_kb_evidence("题干", "kb"))
    assert [s["chunk_id"] for s in out] == ["T1"]  # textbook/standard 优先过滤


def test_stem_kb_grounding_flag_is_opt_in(monkeypatch):
    """默认 OFF（六月五臂 A/B：RAG grounding 伤判分——distractor 抬分同族风险），
    显式 true 才开。"""
    from deeptutor.capabilities import deep_question as dq

    monkeypatch.delenv("LUBAN_STEM_RUBRIC_KB_GROUNDING", raising=False)
    assert dq._stem_rubric_kb_grounding_enabled() is False
    monkeypatch.setenv("LUBAN_STEM_RUBRIC_KB_GROUNDING", "true")
    assert dq._stem_rubric_kb_grounding_enabled() is True
    monkeypatch.setenv("LUBAN_STEM_RUBRIC_KB_GROUNDING", "off")
    assert dq._stem_rubric_kb_grounding_enabled() is False
