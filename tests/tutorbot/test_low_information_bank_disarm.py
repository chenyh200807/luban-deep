"""low_information_exam_query 锁权轮的题面供给收口（loop 级 hermetic）。

病（2026-08-11 live 3/3 复现,4 轮 sink/hint 补丁无效）:锁权轮 fast 路径经
`_maybe_prefetch_grounded_rag`（loop.py 注入点 add_tool_result）把 questions_bank
相似题行（【题目】【选项】【答案】【解析】）喂进模型上下文,模型拿相似题答案冒充
学员点名的某年某题。in-loop rag 结果 sink 上的 redact（已删）接了线但 live 不通电:
fast 政策轮 prefetch 先行注入,模型不再发起 in-loop rag,sink 永不执行。

收口（单一权威）: 检索供给边界 = `RAGAdapterTool.execute` —— prefetch / in-loop /
exact-fast-path 三通路唯一共享的 execute 点,且经 `_set_tool_context` 手握
runtime_metadata。锁权轮它向统一 pipeline 声明 `retrieval_profile=
"unanchored_exam_query"`,pipeline 在同一条管线内不武装 questions_bank + exam
卷面 chunk 两条题目面通道（教材/规范照常）。管线侧真值由
`tests/services/rag/test_unanchored_exam_query_profile.py` 钉住;本文件的
fake pipeline 只复读那份契约。
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
    # 与 live 同构:loop._set_tool_context(loop.py, 先于 prefetch)把整份
    # runtime_metadata 交给工具。
    rag_tool.set_runtime_context(metadata=dict(metadata))
    loop.tools = _Tools(rag_tool)
    loop.context = _Ctx()
    return loop, rag_tool


# --------------------------------------------------------------------------- #
# 红测 1(live 通路②):prefetch 注入的 messages 不得含题库题面/答案钥匙。        #
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
    """供给声明本身(单一决策点在 RAGAdapterTool.execute,不在各调用点)。"""
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
# 红测 2(通路①同一收口):模型自发 in-loop rag 调用(永远不带 profile 键)          #
# 经同一 execute 点,同样必须声明 disarm。                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_model_issued_in_loop_rag_call_is_also_disarmed(monkeypatch) -> None:
    from deeptutor.services.rag.retrieval_profiles import (
        RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY,
    )

    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    rag_tool = RAGAdapterTool()
    rag_tool.set_runtime_context(metadata=dict(_BLOCKED_METADATA))

    result = await rag_tool.execute(query="2025年真题第3题标准答案")

    assert (
        captured["kwargs"].get("retrieval_profile")
        == RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    )
    assert "【答案】" not in str(result)


# --------------------------------------------------------------------------- #
# 守恒钉:非锁权轮逐字节旧行为;调用方显式 profile(案例直通身份轮)不被覆盖。       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unlocked_turn_supply_is_byte_for_byte_unchanged(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    unlocked = {k: v for k, v in _BLOCKED_METADATA.items() if k != "exact_question_blocked_reason"}
    rag_tool = RAGAdapterTool()
    rag_tool.set_runtime_context(metadata=unlocked)

    result = await rag_tool.execute(query=QUERY)

    assert "retrieval_profile" not in captured["kwargs"]
    assert "【答案】" in str(result)  # 正常轮 bank 供给原样(fake 契约的 full 分支)


@pytest.mark.asyncio
async def test_caller_declared_profile_wins_over_disarm(monkeypatch) -> None:
    """案例判分直通身份轮显式声明 case_grading_identity——bank 是它的身份命脉,
    锁权 disarm 不得覆盖调用方声明(两场景本就互斥,此钉防未来交叠时静默改判)。"""
    captured: dict = {}
    monkeypatch.setattr(
        "deeptutor.tools.rag_tool.rag_search", _contract_faithful_rag_search(captured)
    )
    rag_tool = RAGAdapterTool()
    rag_tool.set_runtime_context(metadata=dict(_BLOCKED_METADATA))

    await rag_tool.execute(query=QUERY, retrieval_profile="case_grading_identity")

    assert captured["kwargs"].get("retrieval_profile") == "case_grading_identity"


# --------------------------------------------------------------------------- #
# (b) 假说实证钉:blocked 键在 loop 工具边界时点确实在场——                       #
# _set_tool_context 把整份 runtime_metadata 交给 rag 工具(HEAD 上即绿,           #
# 证明 live 病不是"键缺失"(b),而是 prefetch 通路绕过 sink(a))。                  #
# --------------------------------------------------------------------------- #


def test_set_tool_context_hands_blocked_reason_to_rag_tool(tmp_path) -> None:
    from types import SimpleNamespace

    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class _P(LLMProvider):
        async def chat(self, *_a, **_k):
            return LLMResponse(content="占位")

        def get_default_model(self):
            return "fake"

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_P(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop._set_tool_context(
        "web",
        "chat-1",
        None,
        session_key="web:chat-1",
        metadata=dict(_BLOCKED_METADATA),
    )
    rag_tool = loop.tools.get("rag")
    assert rag_tool is not None
    assert (
        rag_tool._runtime_context.get("exact_question_blocked_reason")
        == "low_information_exam_query"
    )
