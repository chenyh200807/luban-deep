"""Control-plane 治本 Action 2 Step 2 — orchestrator preselect 路径 canonical 必达.

漏点(commander 裁决):orchestrator._select_capability 的 preselect 分支
(`if context.active_capability and not mcq_grading_bypass`)直接 return 预选 capability,
不经过 semantic_router resolve,因此 deep_question 从此入口被路由时 metadata 里**没有**
canonical turn_semantic_decision → deep_question 旧路径会 fabricate 第二权威。

镜像 question_review-no-active 分支(orchestrator.py:~277)已做的注入,在 preselect
分支补 canonical 注入,保证进 deep_question 必带 canonical(defensive 闭合;取证说它
生产没漏,但 fail-fast 退役需要这条入口注入兜底)。

安全带:mcq_grading_bypass / preselect demote 非答题轮 / 非 deep_question 预选 不动。
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.runtime.orchestrator import ChatOrchestrator
from deeptutor.core.context import UnifiedContext


class _FakeCapability:
    async def run(self, context: UnifiedContext, bus: Any) -> None:  # pragma: no cover
        return None


class _FakeRegistry:
    def __init__(self) -> None:
        self.captured: list[str] = []

    def get(self, name: str) -> Any:
        self.captured.append(name)
        return _FakeCapability()

    def list_capabilities(self) -> list[str]:
        return ["chat", "deep_question", "tutorbot"]

    def get_manifests(self) -> list[dict[str, Any]]:
        return []


def _active_single_question(session_id: str) -> dict[str, Any]:
    return {
        "object_type": "single_question",
        "object_id": "q1",
        "scope": {"domain": "session", "session_id": session_id},
        "state_snapshot": {
            "question_id": "q1",
            "question": "某工程屋面坡度最小值是（ ）。",
            "question_type": "choice",
            "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
            "correct_answer": "C",
        },
        "version": 1,
    }


@pytest.mark.asyncio
async def test_preselect_deep_question_submission_supplies_canonical_decision() -> None:
    """漏点核心:preselect 分支的 SUBMISSION 子路径
    (`_prepare_question_submission_context`)旧实现不注入 canonical →
    deep_question fabricate 第二权威。Step 2 后必须注入 canonical,deep_question
    只读它。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    sid = "s-preselect-canonical-submission"
    context = UnifiedContext(
        session_id=sid,
        user_message="我选C",
        active_capability="deep_question",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={"active_object": _active_single_question(sid)},
        language="zh",
    )

    cap = await orchestrator._select_capability(context)
    assert cap == "deep_question"

    supplied = context.metadata.get("turn_semantic_decision")
    assert isinstance(supplied, dict) and supplied, (
        "preselect submission 路径必须注入 canonical decision,"
        "否则 deep_question fabricate 第二权威"
    )
    assert str(supplied.get("next_action") or "").strip() != ""


@pytest.mark.asyncio
async def test_preselect_deep_question_generation_supplies_canonical_decision() -> None:
    """preselect 分支(active_capability=deep_question + practice_generation 续做意图)
    必须注入 canonical turn_semantic_decision,使 deep_question 只读它而非 fabricate。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselect-canonical-gen",
        user_message="再来一道同类的题",
        active_capability="deep_question",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            # generation-continuation 意图 → 命中 preselect 分支(避开 demote)。
            "question_followup_action": {
                "intent": "generate_more_questions",
                "confidence": 1.0,
            },
        },
        language="zh",
    )

    cap = await orchestrator._select_capability(context)
    assert cap == "deep_question"

    supplied = context.metadata.get("turn_semantic_decision")
    assert isinstance(supplied, dict) and supplied, (
        "preselect 路径必须注入 canonical decision,否则 deep_question fabricate 第二权威"
    )
    assert str(supplied.get("next_action") or "").strip() != ""


@pytest.mark.asyncio
async def test_preselect_does_not_overwrite_existing_canonical() -> None:
    """已有 canonical(例如上游 resolve 写入)时,preselect 注入用 setdefault 语义,
    绝不覆盖既有权威。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    existing = {
        "relation_to_active_object": "answer_active_object",
        "next_action": "route_to_grading",
        "allowed_patch": "update_answer_slot",
        "confidence": 1.0,
        "reason": "upstream canonical",
    }
    context = UnifiedContext(
        session_id="s-preselect-keep-existing",
        user_message="A",
        active_capability="deep_question",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={
            "turn_semantic_decision": dict(existing),
            "question_followup_action": {
                "intent": "generate_more_questions",
                "confidence": 1.0,
            },
        },
        language="zh",
    )

    cap = await orchestrator._select_capability(context)
    assert cap == "deep_question"

    supplied = context.metadata.get("turn_semantic_decision")
    assert isinstance(supplied, dict)
    # 既有 canonical 的决策字段不被 preselect 注入覆盖。
    assert supplied.get("next_action") == "route_to_grading"
    assert supplied.get("reason") == "upstream canonical"


@pytest.mark.asyncio
async def test_preselect_non_deep_question_untouched() -> None:
    """安全带:非 deep_question 预选(例如 tutorbot)不注入 canonical decision —
    preselect canonical 必达仅针对 deep_question(structured switch resolver 入口)。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="s-preselect-tutorbot",
        user_message="给我讲讲流水施工",
        active_capability="tutorbot",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={},
        language="zh",
    )

    cap = await orchestrator._select_capability(context)
    assert cap == "tutorbot"
    # tutorbot 是 context-continuous 主 LLM,不依赖 structured canonical decision。
    assert not context.metadata.get("turn_semantic_decision")
