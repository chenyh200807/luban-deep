"""low_information_exam_query 锁权轮的题面供给收口（loop 级 hermetic）。

病（2026-08-11 live 3/3 复现,4 轮 sink/hint 补丁无效）:锁权轮 fast 路径经
`_maybe_prefetch_grounded_rag` 把 questions_bank 相似题行（【题目】【选项】【答案】
【解析】）喂进模型上下文,模型拿相似题答案冒充学员点名的某年某题。

收口后复审(16-agent code review)再收 4 洞,本文件同时钉:
- F1 锁权键滞留:blocked_reason 是 turn-start 决策(orchestrator 唯一写者,本轮写/
  本轮 pop),持久化 session metadata 里的陈旧拷贝必须在入口剥掉(与 turn_failure
  marker 同款 per-turn 纪律)——一次锁权不得让后续合法轮永久失去题库供给。
- F3 并发竞态:disarm 判据不得走共享可变 tool state(RAGAdapterTool._runtime_context
  会被并发轮的 _set_tool_context 覆盖);唯一决策权威 =
  `resolve_turn_retrieval_profile`(纯函数,吃各调用点闭包里的 per-turn
  runtime_metadata),profile 随 args 传递。
- F4 模型绕过:服务端推导压过一切调用方声明;模型自发 rag 调用里未在 schema 声明的
  retrieval_profile kwarg 一律不被尊重(`_prepare_rag_tool_args` 先剥后盖)。
- F5 第五通路:manager 侧 general-knowledge 编译 pack 的「真题」源消费同一 per-turn
  事实,锁权轮被过滤(教材/规范/讲义源照常)。

管线侧真值由 `tests/services/rag/test_unanchored_exam_query_profile.py` 钉住;
本文件的 fake pipeline 只复读那份契约。
"""

from __future__ import annotations

import json

import pytest

from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

QUERY = "2025年一建建筑实务真题第3题的答案是什么？"

_BANK_STEM = "混凝土结构工程施工中,同条件养护试件的留置组数应满足（ ）。"
_BANK_TEXT = (
    f"【题目】{_BANK_STEM}\n"
    '【选项】[{"key": "A", "value": "15MPa"}, {"key": "B", "value": "10MPa"}]\n'
    "【答案】A\n【解析】正确答案: A,依据教材……"
)
_BANK_SOURCE = {
    "chunk_id": "question-9502",
    "rag_content": _BANK_TEXT,
    "source_type": "exam",
    "content_type": "question",
    "_source_group": "questions_bank",
    "_source_table": "questions_bank",
}
_TEXTBOOK_TEXT = "教材:混凝土强度检验评定应符合验收规范要求……"

_BLOCKED_METADATA = {
    "bot_id": "construction-exam-coach",
    "default_tools": ["rag"],
    "default_kb": "construction-exam",
    "knowledge_bases": ["construction-exam"],
    "effective_response_mode": "fast",
    "execution_path": "tutorbot_kb_first_fast_policy",
    "exact_question_blocked_reason": "low_information_exam_query",
}


def _contract_faithful_rag_search(captured: dict):
    """复读管线契约的 fake `rag_search`:未声明 disarm profile 时返回 bank 相似题
    （HEAD 病灶输入）,声明后 bank/exam 通道不武装、只剩教材正文。"""

    async def fake_rag_search(query: str, kb_name=None, **kwargs):
        captured["query"] = query
        captured["kwargs"] = dict(kwargs)
        if str(kwargs.get("retrieval_profile") or "") == "unanchored_exam_query":
            return {
                "answer": _TEXTBOOK_TEXT,
                "content": _TEXTBOOK_TEXT,
                "sources": [
                    {
                        "chunk_id": "kb-textbook",
                        "rag_content": _TEXTBOOK_TEXT,
                        "source_type": "textbook",
                        "_source_group": "textbook",
                    }
                ],
                "exact_question": {},
                "retrieval_profile": "unanchored_exam_query",
            }
        return {
            "answer": _BANK_TEXT,
            "content": _BANK_TEXT,
            "sources": [dict(_BANK_SOURCE)],
            "exact_question": {},
            "retrieval_profile": "full",
        }

    return fake_rag_search


class _Ctx:
    def build_messages(self, *, history, current_message, **_kwargs):
        return [{"role": "system", "content": ""}, *history, {"role": "user", "content": current_message}]

    def add_assistant_message(self, messages, content, **kwargs):
        item = {"role": "assistant", "content": content}
        if kwargs.get("tool_calls") is not None:
            item["tool_calls"] = kwargs["tool_calls"]
        return [*messages, item]

    def add_tool_result(self, messages, tool_call_id, tool_name, result):
        return [
            *messages,
            {"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result},
        ]


class _Tools:
    """真 RAGAdapterTool 挂进最小注册表——收口点必须是真被测对象,不是手写替身。"""

    def __init__(self, rag_tool: RAGAdapterTool) -> None:
        self._rag = rag_tool
        self.tool_names = ["rag"]

    def get(self, name):
        return self._rag if name == "rag" else None

    async def execute(self, name, args):
        assert name == "rag"
        return await self._rag.execute(**args)


def _prefetch_loop(metadata: dict) -> tuple[AgentLoop, RAGAdapterTool]:
    loop = AgentLoop.__new__(AgentLoop)
    rag_tool = RAGAdapterTool()
    rag_tool.set_runtime_context(metadata=dict(metadata))
    loop.tools = _Tools(rag_tool)
    loop.context = _Ctx()
    return loop, rag_tool


# --------------------------------------------------------------------------- #
# live 通路②:prefetch 注入的 messages 不得含题库题面/答案钥匙。                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_prefetch_messages_carry_no_bank_surface_on_locked_turn(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    loop, _ = _prefetch_loop(_BLOCKED_METADATA)
    md = dict(_BLOCKED_METADATA)

    messages = await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": QUERY}],
        current_message=QUERY,
        runtime_metadata=md,
    )

    joined = json.dumps(messages, ensure_ascii=False)
    assert "【答案】" not in joined and "【解析】" not in joined, (
        "锁权轮题库答案钥匙进了模型上下文(冒充病的弹药): " + joined[:400]
    )
    assert _BANK_STEM not in joined, "锁权轮题库题面进了模型上下文(归属冒充的弹药)"
    # 教材通道照常武装:模型仍有讲解依据,不是拒答降级。
    assert _TEXTBOOK_TEXT in joined


@pytest.mark.asyncio
async def test_prefetch_supply_declares_disarm_profile_on_locked_turn(monkeypatch) -> None:
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    loop, _ = _prefetch_loop(_BLOCKED_METADATA)

    await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": QUERY}],
        current_message=QUERY,
        runtime_metadata=dict(_BLOCKED_METADATA),
    )

    assert (
        captured["kwargs"].get("retrieval_profile")
        == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )


# --------------------------------------------------------------------------- #
# F3+F4:单一决策权威 = 纯函数 resolve_turn_retrieval_profile,per-turn 传参。     #
# --------------------------------------------------------------------------- #


def test_resolver_is_a_pure_per_turn_function() -> None:
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
        resolve_turn_retrieval_profile,
    )

    assert (
        resolve_turn_retrieval_profile(dict(_BLOCKED_METADATA))
        == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    assert resolve_turn_retrieval_profile({}) == ""
    assert resolve_turn_retrieval_profile(None) == ""
    # 非锁权轮:调用方显式声明原样透传(案例直通身份轮)。
    assert (
        resolve_turn_retrieval_profile({}, "case_grading_identity")
        == "case_grading_identity"
    )


def test_server_derived_disarm_overrides_caller_declared_profile() -> None:
    """F4 翻转优先级:服务端推导压过一切调用方声明——锁权事实是 lifecycle gate
    唯一写的数据面否决,不给任何调用方(更不给模型)留逃生舱。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
        resolve_turn_retrieval_profile,
    )

    for declared in ("full", "case_grading_identity", "unknown_profile"):
        assert (
            resolve_turn_retrieval_profile(dict(_BLOCKED_METADATA), declared)
            == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
        )


def test_model_authored_retrieval_profile_kwarg_is_never_honored() -> None:
    """F4:模型自发 rag 调用的 args 是不受信任输入;schema 未声明的
    retrieval_profile kwarg 一律剥掉,再按本轮事实盖章。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    # 锁权轮:模型注入 "full" 妄图重新武装 → 强制 disarm。
    stamped = AgentLoop._prepare_rag_tool_args(
        {"query": "2025年真题第3题标准答案", "retrieval_profile": "full"},
        dict(_BLOCKED_METADATA),
    )
    assert stamped["retrieval_profile"] == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    # 非锁权轮:模型声明的 profile 同样不被尊重(undeclared param)。
    clean = AgentLoop._prepare_rag_tool_args(
        {"query": "混凝土强度", "retrieval_profile": "case_grading_identity"},
        {},
    )
    assert "retrieval_profile" not in clean
    assert clean["query"] == "混凝土强度"


@pytest.mark.asyncio
async def test_disarm_rides_args_and_survives_concurrent_context_overwrite(monkeypatch) -> None:
    """F3:并发轮 _set_tool_context 覆盖共享 _runtime_context 后,A 轮已按自身
    per-turn metadata 盖章的 args 仍然 disarm——判据不走共享可变 tool state。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    rag_tool = RAGAdapterTool()
    # A 轮(锁权)盖章后,B 轮并发覆盖共享 context 为干净 metadata:
    a_args = AgentLoop._prepare_rag_tool_args({"query": QUERY}, dict(_BLOCKED_METADATA))
    rag_tool.set_runtime_context(metadata={"default_kb": "construction-exam"})

    result = await rag_tool.execute(**a_args)

    assert (
        captured["kwargs"].get("retrieval_profile")
        == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    assert "【答案】" not in str(result)


@pytest.mark.asyncio
async def test_adapter_does_not_derive_disarm_from_shared_runtime_context(monkeypatch) -> None:
    """F3 反面钉:adapter 不再从共享 _runtime_context 推导 disarm(那是竞态源)。
    未盖章的 args + 锁权 context → 不注入 profile(收口责任全在 per-turn 盖章点)。"""
    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    rag_tool = RAGAdapterTool()
    rag_tool.set_runtime_context(metadata=dict(_BLOCKED_METADATA))

    await rag_tool.execute(query=QUERY)

    assert "retrieval_profile" not in captured["kwargs"]


# --------------------------------------------------------------------------- #
# F1:锁权键 per-turn 纪律——陈旧拷贝入口剥离,下一合法轮恢复题库供给。             #
# --------------------------------------------------------------------------- #


def test_stale_blocked_reason_is_stripped_from_session_inherited_metadata() -> None:
    from deeptutor.services.question_lifecycle_skills import (
        strip_stale_question_lifecycle_turn_metadata,
    )

    stale = {"exact_question_blocked_reason": "low_information_exam_query", "default_kb": "k"}
    strip_stale_question_lifecycle_turn_metadata(stale)
    assert "exact_question_blocked_reason" not in stale
    assert stale["default_kb"] == "k"


def test_loop_turn_metadata_seam_never_inherits_blocked_reason_from_session() -> None:
    """loop 入口 seam(dict(session.metadata) → strip → update(msg.metadata)):
    per-turn 信道(msg.metadata)是 blocked 事实唯一入口;session 持久层的陈旧拷贝
    不得漏进本轮。"""
    inherited = AgentLoop._build_turn_runtime_metadata(
        dict(_BLOCKED_METADATA),  # 上一锁权轮被 manager 持久化进 session.metadata
        {"raw_user_message": _BANK_STEM + " 我选A对吗?"},  # 本轮合法作答,无 blocked 键
    )
    assert "exact_question_blocked_reason" not in inherited

    blocked_turn = AgentLoop._build_turn_runtime_metadata(
        {"default_kb": "construction-exam"},
        dict(_BLOCKED_METADATA),  # 本轮确实锁权:per-turn 信道带键
    )
    assert (
        blocked_turn["exact_question_blocked_reason"] == "low_information_exam_query"
    )


def test_next_legitimate_turn_restores_bank_supply() -> None:
    """F1 复原钉(两轮序列):锁权轮 disarm → 键随 merged metadata 持久化 →
    下一合法轮(学员补发完整题干)必须恢复题库供给(profile 为空 = bank 武装)。"""
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
        resolve_turn_retrieval_profile,
    )

    # 轮 1:锁权。
    turn1 = AgentLoop._build_turn_runtime_metadata({}, dict(_BLOCKED_METADATA))
    assert (
        resolve_turn_retrieval_profile(turn1) == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    # manager.send_message 把 merged metadata(含键)写回 session.metadata 并保存。
    persisted_session_metadata = dict(turn1)

    # 轮 2:学员补发完整题干+选项,lifecycle 不再 blocked(orchestrator pop 了键),
    # per-turn 信道无键;session 里滞留的是轮 1 的陈旧拷贝。
    turn2 = AgentLoop._build_turn_runtime_metadata(
        persisted_session_metadata,
        {"raw_user_message": _BANK_STEM + " A.15MPa B.10MPa 我选A"},
    )
    assert resolve_turn_retrieval_profile(turn2) == "", (
        "锁权键滞留 session:合法轮题库供给未恢复(F1 回归——一次锁权,全会话失供)"
    )


# --------------------------------------------------------------------------- #
# F5:第五通路——manager 侧 general-knowledge 编译 pack 的「真题」源。            #
# --------------------------------------------------------------------------- #


def _teaching_pack() -> dict:
    return {
        "leaf_name_path": "项目施工进度管理/双代号网络图",
        "confidence": {"status": "high", "policy": "leaf_exact", "reason": "high"},
        "sources": {
            "textbook": [
                {"text_preview": "教材:双代号网络图的绘制规则……", "title": "教材"}
            ],
            "question": [
                {"text_preview": "真题:2020年管理第22题 双代号网络图计算工期,答案C", "title": "真题"}
            ],
        },
    }


def test_general_knowledge_pack_question_source_disarmed_on_locked_turn(monkeypatch) -> None:
    from deeptutor.services.tutorbot import manager as manager_module

    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", raising=False)
    monkeypatch.setattr(
        manager_module,
        "resolve_general_knowledge_context",
        lambda content, learner_context=None: _teaching_pack(),
    )
    md = {
        **_BLOCKED_METADATA,
        "general_knowledge_context": True,  # 显式 opt-in,绕开 cohort 门
        "user_id": "student-1",
    }
    manager_module._attach_general_knowledge_context(
        content="2020年一建管理双代号网络图那道真题的答案", runtime_metadata=md
    )

    grounding = str(md.get("conversation_context_text") or "")
    pack = md.get("luban_general_knowledge_context") or {}
    assert "答案C" not in grounding and "真题:2020年管理第22题" not in grounding, (
        "锁权轮 general-knowledge pack 的真题源进了 grounding(F5 第五通路)"
    )
    assert not (pack.get("sources") or {}).get("question"), "存储 pack 仍带真题源"
    # 教材源照常(概念讲解不受影响)。
    assert "双代号网络图的绘制规则" in grounding


def test_general_knowledge_pack_untouched_on_unlocked_turn(monkeypatch) -> None:
    from deeptutor.services.tutorbot import manager as manager_module

    monkeypatch.delenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", raising=False)
    monkeypatch.setattr(
        manager_module,
        "resolve_general_knowledge_context",
        lambda content, learner_context=None: _teaching_pack(),
    )
    md = {
        "general_knowledge_context": True,
        "user_id": "student-1",
        "bot_id": "construction-exam-coach",
    }
    manager_module._attach_general_knowledge_context(
        content="双代号网络图怎么算工期", runtime_metadata=md
    )
    grounding = str(md.get("conversation_context_text") or "")
    assert "真题:2020年管理第22题" in grounding  # 非锁权轮逐字节旧行为
