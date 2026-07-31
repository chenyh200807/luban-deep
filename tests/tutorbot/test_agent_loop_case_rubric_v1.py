"""TutorBot loop V1 case-grading integration (`_v1_case_render` / `_build_v1_case_ctx` /
`_apply_v1_or_case_fallback`).

Hermetic: rubric_grader_v1.load_rubric + batch_judge_async stubbed (no LLM). Proves V1 takes over the
TutorBot case-grading turn when score authority + flag are present (becoming the score authority),
extracts the case reference from covered_subquestions[].authoritative_answer, and stays inert otherwise
(non-case scene / no authority / flag off) so non-grading turns are byte-identical.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.services.construction_grading import rubric_grader_v1 as G
from deeptutor.tutorbot.agent.loop import AgentLoop
from deeptutor.tutorbot.bus.events import InboundMessage
from deeptutor.tutorbot.session.manager import Session


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
            "node_code": "1A432000",
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


class _FakeContext:
    def build_messages(self, *, history, current_message, media=None, channel=None, chat_id=None, runtime_instruction=None):
        return [{"role": "system", "content": ""}, *history, {"role": "user", "content": current_message}]

    def add_assistant_message(self, messages, content, **_kwargs):
        item = {"role": "assistant", "content": content}
        if _kwargs.get("tool_calls") is not None:
            item["tool_calls"] = _kwargs["tool_calls"]
        return [*messages, item]

    def add_tool_result(self, messages, tool_call_id, tool_name, result):
        return [
            *messages,
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": result,
            },
        ]


def test_save_turn_persists_raw_user_message_instead_of_context_envelope() -> None:
    loop = _loop()
    session = Session(key="web:case")
    envelope = (
        "## 参考证据\n"
        "以下内容是辅助证据，不得覆盖当前用户问题与当前会话锚点。\n\n"
        "### 局部工作记忆投影\n"
        "这段只应注入给 LLM，不应进入 TutorBot mirror session。\n\n"
        "## 当前用户问题\n"
        "防水卷材搭接宽度怎么记？"
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": envelope},
        {"role": "assistant", "content": "先按材料和施工方法区分。"},
    ]

    loop._save_turn(
        session,
        messages,
        skip=1,
        persist_user_content="防水卷材搭接宽度怎么记？",
    )

    assert [item["role"] for item in session.messages] == ["user", "assistant"]
    assert session.messages[0]["content"] == "防水卷材搭接宽度怎么记？"
    assert "参考证据" not in session.messages[0]["content"]


def _make_loop_fixtures(tmp_path, provider):
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus

    class DummyTool(Tool):
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "dummy tool"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            }

        async def execute(self, **kwargs: Any) -> str:
            self.calls.append(dict(kwargs))
            return f"executed:{kwargs['topic']}"

    tool = DummyTool()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=5,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(tool)
    return loop, tool


def _tool_aware_provider():
    """Provider that searches while tool use is allowed and answers once the
    closure round forces tool_choice="none" — the cooperative shape the
    closure-round contract expects."""
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class ToolAwareProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.tools_seen: list[int] = []
            self.tool_choices_seen: list[Any] = []

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            self.tools_seen.append(len(tools or []))
            self.tool_choices_seen.append(tool_choice)
            self.max_tokens_seen = max_tokens
            if tools and tool_choice != "none":
                return LLMResponse(
                    content="继续调用工具",
                    tool_calls=[
                        ToolCallRequest(
                            id=f"call_{self.calls}",
                            name="rag",
                            arguments={"topic": f"round-{self.calls}"},
                        )
                    ],
                )
            return LLMResponse(content="基于已检索证据：不妥之处是排水坡度 0.1% 偏小，正确做法是不小于 0.2%。")

        def get_default_model(self) -> str:
            return "fake-model"

    return ToolAwareProvider()


@pytest.mark.asyncio
async def test_exhausted_tool_budget_runs_closure_round_and_synthesizes_answer(tmp_path) -> None:
    """Fall-through-to-understanding: when every budgeted round was a search, one
    extra closure round (tools kept for prompt-cache prefix, tool_choice="none")
    must answer from gathered evidence instead of failing closed to the canned
    template (production session unified_1785314628533_23c29374: 4/4 rounds
    searched, 142k tokens of evidence discarded into a refusal)."""
    provider = _tool_aware_provider()
    loop, tool = _make_loop_fixtures(tmp_path, provider)
    metadata = {
        "default_tools": ["rag"],
        "mode_execution_policy": {"max_tool_rounds": 2},
    }

    final_content, tools_used, messages = await loop._run_agent_loop(
        [{"role": "user", "content": "一直调用工具"}],
        runtime_metadata=metadata,
    )

    assert provider.calls == 3  # 2 budgeted search rounds + 1 closure round
    # Deep answers use the wired 8192 cap (AgentDefaults.max_tokens was dead
    # config; provider GenerationSettings default 4096 truncates long
    # multi-subquestion closure answers).
    assert provider.max_tokens_seen == 8192
    # Closure round keeps the tools block (prompt-cache prefix stability) and
    # relies on server-enforced tool_choice="none".
    assert provider.tools_seen == [1, 1, 1]
    assert provider.tool_choices_seen == [None, None, "none"]
    assert tools_used == ["rag", "rag"]
    assert tool.calls == [{"topic": "round-1"}, {"topic": "round-2"}]
    assert final_content is not None and "基于已检索证据" in final_content
    assert "turn_failure" not in metadata
    assert metadata["forced_closure_round"] == 3
    assert any(
        item.get("role") == "system" and "收束作答" in str(item.get("content") or "")
        for item in messages
    )


@pytest.mark.asyncio
async def test_stubborn_tool_calls_on_closure_round_stay_typed_failure(tmp_path) -> None:
    """Safety net (律4): a provider that ignores tool_choice="none" and keeps
    emitting pure tool calls still yields a TYPED failure — closure-round tool
    calls are never executed and never accepted as an answer."""
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class StubbornProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id=f"call_{self.calls}",
                        name="rag",
                        arguments={"topic": f"round-{self.calls}"},
                    )
                ],
            )

        def get_default_model(self) -> str:
            return "fake-model"

    provider = StubbornProvider()
    loop, tool = _make_loop_fixtures(tmp_path, provider)
    metadata = {
        "default_tools": ["rag"],
        "mode_execution_policy": {"max_tool_rounds": 2},
    }

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "一直调用工具"}],
        runtime_metadata=metadata,
    )

    # 2 search rounds + closure round + visible-answer repair retry.
    assert provider.calls == 4
    # Closure-round and repair-round tool calls are never recorded or executed.
    assert tools_used == ["rag", "rag"]
    assert tool.calls == [{"topic": "round-1"}, {"topic": "round-2"}]
    assert metadata["effective_max_tool_rounds"] == 2
    assert metadata["forced_closure_round"] == 3
    assert final_content is None
    assert metadata["turn_failure"]["kind"] == "model_empty_answer"


@pytest.mark.asyncio
async def test_single_round_policy_keeps_tools_and_budget_semantics(tmp_path) -> None:
    """max_tool_rounds == 1 (fast policy shape): the only round keeps its tools
    armed and no closure round is appended."""
    provider = _tool_aware_provider()
    loop, tool = _make_loop_fixtures(tmp_path, provider)
    metadata = {
        "default_tools": ["rag"],
        "mode_execution_policy": {"max_tool_rounds": 1},
    }

    final_content, tools_used, messages = await loop._run_agent_loop(
        [{"role": "user", "content": "一直调用工具"}],
        runtime_metadata=metadata,
    )

    assert provider.calls == 1
    assert provider.tools_seen == [1]
    assert provider.tool_choices_seen == [None]
    assert tools_used == ["rag"]
    assert tool.calls == [{"topic": "round-1"}]
    assert "forced_closure_round" not in metadata
    assert not any(
        item.get("role") == "system" and "收束作答" in str(item.get("content") or "")
        for item in messages
    )
    assert final_content is None
    assert metadata["turn_failure"]["kind"] == "tool_budget_exhausted"
    assert metadata["turn_failure"]["budget"] == 1


@pytest.mark.asyncio
async def test_prefetch_round_seeds_saturation_and_first_round_keeps_rag(
    tmp_path,
) -> None:
    """收权回归（2026-07-29）：防冗余检索的唯一权威是 rag_saturation。
    ①首轮不再暗藏 rag（旧的 prefetched_rag_satisfied 首轮抑制曾让模型白烧一轮吃
    "Tool 'rag' is not available"，生产事故实证）；②预取轮播种进 saturation 账本，
    模型复读预取 query 时立即饱和，下一轮才摘 rag。"""
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    captured: dict[str, list[list[str]]] = {"tool_name_sets": []}

    class ReplayingProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            model: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.7,
            reasoning_effort: str | None = None,
            tool_choice: str | dict[str, Any] | None = None,
            on_content_delta=None,
        ) -> LLMResponse:
            self.calls += 1
            captured["tool_name_sets"].append(
                [
                    str(item.get("function", {}).get("name") or "")
                    for item in list(tools or [])
                ]
            )
            if self.calls == 1:
                # 复读预取 query（相似度 1.0、源重合 1.0）→ 应触发饱和。
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest(
                            id="call_1",
                            name="rag",
                            arguments={"query": "临时用水 消火栓间距 排水坡度"},
                        )
                    ],
                )
            return LLMResponse(content="基于已召回证据回答。")

        def get_default_model(self) -> str:
            return "fake-model"

    class TracingRagTool(Tool):
        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "dummy"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return "重复证据"

        def consume_trace_metadata(self) -> dict[str, Any] | None:
            return {"sources": [{"chunk_id": "S1"}, {"chunk_id": "S2"}]}

    class DummyTool(Tool):
        def __init__(self, name: str) -> None:
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        @property
        def description(self) -> str:
            return "dummy"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

        async def execute(self, **kwargs: Any) -> str:
            return str(kwargs)

    loop = AgentLoop(
        bus=MessageBus(),
        provider=ReplayingProvider(),
        workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    loop.tools = TutorBotToolRegistry()
    loop.tools.register(TracingRagTool())
    loop.tools.register(DummyTool("web_search"))
    metadata = {
        "default_tools": ["rag", "web_search"],
        "prefetched_rag_satisfied": True,
        "_latest_rag_trace_metadata": {
            "rag_round": {
                "round_index": 1,
                "query": "临时用水 消火栓间距 排水坡度",
                "sources": [{"chunk_id": "S1"}, {"chunk_id": "S2"}],
            }
        },
    }

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "案例题采分点怎么答？"}],
        runtime_metadata=metadata,
    )

    assert final_content == "基于已召回证据回答。"
    # ①首轮 rag 保持在工具列表里（不再暗藏）。
    assert captured["tool_name_sets"][0] == ["rag", "web_search"]
    # ②复读预取 query 的调用被执行一次后触发饱和，下一轮 rag 被摘除。
    assert tools_used == ["rag"]
    assert captured["tool_name_sets"][1] == ["web_search"]
    assert "prefetched_rag_suppressed_first_loop" not in metadata
    # ③饱和必须显式告知模型（不许无声藏工具——重试跑步机的根源），
    # 且只注入一次。
    notices = [
        item
        for item in _messages
        if item.get("role") == "system" and "检索已饱和" in str(item.get("content") or "")
    ]
    assert len(notices) == 1
    # ④协议序列不变量（review B-1）：assistant(tool_calls) 后必须紧跟其全部
    # tool 结果，任何 system 消息不得插入中间——OpenAI-strict provider 会 400。
    for idx, item in enumerate(_messages):
        if item.get("role") == "assistant" and item.get("tool_calls"):
            tool_call_count = len(item["tool_calls"])
            followers = _messages[idx + 1 : idx + 1 + tool_call_count]
            assert [f.get("role") for f in followers] == ["tool"] * tool_call_count


def test_build_v1_case_ctx_extracts_reference_from_covered_subquestions() -> None:
    ctx = AgentLoop._build_v1_case_ctx(_case_md(), "我的作答：共用一个开关箱不妥")
    assert ctx["question_id"] == "CASE-1"
    assert ctx["construction_grading_result"]["type"] == "case"
    # reference comes from covered_subquestions[].authoritative_answer (NOT top-level correct_answer)
    assert "共用一个开关箱" in ctx["correct_answer"]
    assert "应编制临时用电施工组织设计" in ctx["correct_answer"]
    assert ctx["user_answer"].startswith("我的作答")
    assert ctx["node_code"] == "1A432000"


def test_build_v1_case_ctx_uses_current_full_submission_marked_reference() -> None:
    md = {"question_lifecycle_scene": "case_grading", "user_id": "qa_loop_v1"}
    message = (
        "案例题：某工程底模拆除时混凝土强度检查。\n"
        "问题：跨度为8m的现浇梁底模拆除时，混凝土强度应达到设计强度的多少？"
        "我的答案：75%。标准答案：100%。请判分。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["correct_answer"] == "100%"
    assert ctx["user_answer"] == "75%"
    assert "标准答案" not in ctx["user_answer"]
    assert "底模拆除" in ctx["question_stem"]


def test_build_v1_case_ctx_splits_full_case_submission_and_blocks_mismatched_exact() -> None:
    md = _case_md()
    md["_prefetched_exact_question"] = {
        "answer_kind": "case_study",
        "question_id": "WRONG-CASE",
        "stem": "固定总价合同风险范围和违约条款案例。",
        "covered_subquestions": [
            {"authoritative_answer": "应明确包死价种类、风险范围、违约条款，结算价为121520.00元。"},
        ],
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？2. 中标单位还应避免哪些违法分包行为？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。\n"
        "3. 不得分包给不具备资质单位。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == ""
    assert ctx["correct_answer"] == ""
    assert "工程量清单的强制性内容" in ctx["question_stem"]
    assert ctx["user_answer"].startswith("1. 工程量计算规则")
    assert "建设单位编制了投资兴建某工程" not in ctx["user_answer"]
    assert md["exact_question_blocked_reason"] == "case_exact_mismatch"


def test_build_v1_case_ctx_blocks_exact_reference_when_subquestions_do_not_match_current_submission() -> None:
    md = _case_md()
    md["_prefetched_exact_question"] = {
        "answer_kind": "case_study",
        "question_id": "",
        "stem": "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。",
        "covered_subquestions": [
            {
                "question": "采用固定价格应注意明确哪些事项？",
                "authoritative_answer": "应明确包死价种类、风险范围、风险费用计算方法和违约条款。",
            },
            {
                "question": "计算措施费、安全文明施工费和签约合同价。",
                "authoritative_answer": "措施费1488万元，安全文明施工费558万元，签约合同价12345万元。",
            },
        ],
        "max_score": 10,
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】\n"
        "1. 工程量清单的强制性内容还有哪些？\n"
        "2. 投标单位对招标文件要求作出实质性响应的内容还有哪些？\n"
        "3. 中标单位还应避免哪些违法分包行为？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。\n"
        "2. 工期；质量标准；投标有效期。\n"
        "3. 不得分包给不具备资质单位。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == ""
    assert ctx["correct_answer"] == ""
    assert "固定价格" not in ctx["correct_answer"]
    assert md["exact_question_blocked_reason"] == "case_exact_mismatch"


def test_build_v1_case_ctx_full_submission_blocks_stale_followup_reference() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "STALE-CASE",
            "question_stem": "固定总价合同风险范围和违约条款案例。",
            "correct_answer": "应明确包死价种类、风险范围、违约条款，结算价为121520.00元。",
            "user_answer": "上一轮旧答案",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？2. 实质性响应内容有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。\n"
        "2. 工期；质量标准；投标有效期。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == ""
    assert ctx["correct_answer"] == ""
    assert "工程量清单的强制性内容" in ctx["question_stem"]
    assert ctx["user_answer"].startswith("1. 工程量计算规则")
    assert ctx["user_answer"] != "上一轮旧答案"
    assert md["case_reference_blocked_reason"] == "full_submission_without_verified_reference"


def test_build_v1_case_ctx_full_submission_blocks_similar_stale_followup_reference() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "SIMILAR-STALE-CASE",
            "question_stem": (
                "某工程采用工程量清单计价，投标人应对招标文件工期、质量和投标有效期"
                "作出实质性响应。"
            ),
            "correct_answer": "固定总价合同应明确风险范围、包死价种类和违约责任。",
            "user_answer": "旧答案",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？2. 投标实质性响应内容还有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。\n"
        "2. 工期；质量标准；投标有效期。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == ""
    assert ctx["correct_answer"] == ""
    assert ctx["user_answer"].startswith("1. 工程量计算规则")
    assert md["case_reference_blocked_reason"] == "full_submission_without_verified_reference"


def test_build_v1_case_ctx_full_submission_keeps_item_only_followup_reference() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "CURRENT-CASE",
            "items": [
                {
                    "question_id": "CURRENT-CASE-1",
                    "question": "1. 工程量清单的强制性内容还有哪些？",
                    "correct_answer": "项目编码、项目名称、项目特征、计量单位和工程量。",
                }
            ],
            "correct_answer": "项目编码、项目名称、项目特征、计量单位和工程量。",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == "CURRENT-CASE-1"
    assert "项目编码" in ctx["correct_answer"]
    assert ctx["user_answer"].startswith("1. 工程量计算规则")
    assert "case_reference_blocked_reason" not in md


def test_build_v1_case_ctx_full_submission_does_not_use_flat_reference_from_item_match() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "MIXED-CASE",
            "items": [
                {
                    "question_id": "MIXED-CASE-1",
                    "question": "1. 工程量清单的强制性内容还有哪些？",
                    "correct_answer": "项目编码、项目名称、项目特征、计量单位和工程量。",
                }
            ],
            "correct_answer": "应明确包死价种类、风险范围、违约条款，签约合同价为12345万元。",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert "项目编码" in ctx["correct_answer"]
    assert "包死价" not in ctx["correct_answer"]
    assert "12345" not in ctx["correct_answer"]


def test_build_v1_case_ctx_full_submission_blocks_flat_reference_without_current_item_answer() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "MIXED-CASE-NO-ITEM-ANSWER",
            "items": [
                {
                    "question_id": "MIXED-CASE-1",
                    "question": "1. 工程量清单的强制性内容还有哪些？",
                }
            ],
            "correct_answer": "应明确包死价种类、风险范围、违约条款，签约合同价为12345万元。",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["correct_answer"] == ""
    assert md["case_reference_blocked_reason"] == "full_submission_without_current_reference_answer"


def test_build_v1_case_ctx_full_submission_blocks_item_only_shared_background_reference() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_loop_v1",
        "followup_question_context": {
            "question_id": "STALE-SHARED-BACKGROUND",
            "items": [
                {
                    "question_id": "STALE-BACKGROUND-ONLY",
                    "question": "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。",
                    "correct_answer": "项目编码、项目名称、项目特征、计量单位和工程量。",
                }
            ],
            "correct_answer": "项目编码、项目名称、项目特征、计量单位和工程量。",
            "max_score": 10,
        },
    }
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】1. 投标单位实质性响应内容还有哪些？\n"
        "回答\n"
        "作答：\n"
        "1. 工期；质量标准；投标有效期。"
    )

    ctx = AgentLoop._build_v1_case_ctx(md, message)

    assert ctx["question_id"] == ""
    assert ctx["correct_answer"] == ""
    assert ctx["user_answer"].startswith("1. 工期")
    assert md["case_reference_blocked_reason"] == "full_submission_without_verified_reference"


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
    assert "## 批改结论" in render and "得分预估：" in render          # V1 render, not the agent's free text
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
async def test_v1_case_stream_plan_derives_diagnostic_for_unbanked_full_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [])
    captured: dict[str, str] = {}

    async def _fake_derive(stem, complete_fn, api_key, *, model="deepseek-chat", provider_authority="", kb_evidence=None):
        captured["stem"] = stem
        captured["provider_authority"] = provider_authority
        return [
            {"point_id": "P1", "text": "工程量清单强制性内容应包括项目编码", "score": 1.0,
             "policy": "qualitative", "required_terms": [], "question_no": 1},
            {"point_id": "P2", "text": "中标单位不得分包给不具备资质单位", "score": 1.0,
             "policy": "qualitative", "required_terms": [], "question_no": 3},
        ]

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        return {
            "P1": {"status": G.MISS},
            "P2": {"status": G.HIT, "evidence_span": "不得分包给不具备资质单位"},
        }

    monkeypatch.setattr(G, "derive_rubric_from_stem_async", _fake_derive)
    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    monkeypatch.setattr(AgentLoop, "_record_v1_grading_to_brain", staticmethod(lambda **_kwargs: None))
    monkeypatch.setattr(AgentLoop, "_schedule_v1_grading_personalization", lambda self, runtime_metadata: None)

    md = {"question_lifecycle_scene": "case_grading", "user_id": "qa_loop_v1"}
    message = (
        "建设单位编制了投资兴建某工程的招标文件，报价采用工程量清单计价。\n"
        "【问题】\n"
        "1. 工程量清单的强制性内容还有哪些？\n"
        "3. 中标单位还应避免哪些违法分包行为？\n"
        "回答\n"
        "作答：\n"
        "1. 工程量计算规则；工程量清单编制方法。\n"
        "3. 不得分包给不具备资质单位。"
    )

    plan = await _loop()._v1_case_stream_plan(runtime_metadata=md, user_message=message)

    assert plan is not None
    assert "诊断得分预估" in plan["score_first"]
    assert "未命中题库原题/标准答案" in plan["score_first"]
    assert md["score_authority"] == "rubric_scored_v1_diagnostic"
    assert md["grading_rubric_provenance"] == "derived_from_stem"
    assert md["grading_official_score_allowed"] is False
    assert "工程量清单的强制性内容" in captured["stem"]
    assert "作答" not in captured["stem"]


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
    assert "## 批改结论" in render


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


def test_case_grading_never_replaced_by_exact_standard_answer() -> None:
    md = {
        "question_lifecycle_scene": "case_grading",
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "coverage_ratio": 1.0,
            "missing_subquestions": [],
            "covered_subquestions": [
                {
                    "subquestion_number": "5",
                    "stem": "计算施工单位结算造价。",
                    "authoritative_answer": "施工单位结算造价为8050.00万元。",
                }
            ],
        },
    }

    assert (
        _loop()._case_exact_authority_fallback(
            "逐采分点点评：结算造价计算式不完整，本小问漏计设备暂估价调整。",
            runtime_metadata=md,
        )
        == ""
    )


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
    # 新契约（P0 2026-07-29）：实质内容不再被模板整篇替换——硬分口径以追加免责
    # 声明降级，正文保留。
    assert out == "" or ("评分口径说明" in out and out.startswith("得分：3分"))


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
    assert "## 批改结论" in out                                      # V1 took over (not the agent text)
    assert md.get("_v1_case_graded") is True


@pytest.mark.asyncio
async def test_v1_case_stream_plan_exports_dynamic_adjudication_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {
            "point_id": f"Q{question_no}-P{idx}",
            "text": f"问题{question_no}采分点{idx}",
            "score": 1.0,
            "policy": "list",
            "required_terms": [],
            "question_no": question_no,
        }
        for question_no in range(1, 7)
        for idx in range(1, 5)
    ])
    call_sizes: list[int] = []

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        call_sizes.append(len(points))
        return {str(point["point_id"]): {"status": G.HIT} for point in points}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    md = _case_md()

    plan = await _loop()._v1_case_stream_plan(runtime_metadata=md, user_message="完整作答")

    assert plan is not None
    assert call_sizes == [8, 8, 8]
    assert md["case_grading_adjudication_strategy"] == "dynamic_parallel_question_groups"
    assert md["case_grading_adjudication_group_count"] == 3
    assert md["case_grading_adjudication_point_count"] == 24


@pytest.mark.asyncio
async def test_case_grading_direct_path_streams_preview_and_returns_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = _loop()
    loop.context = _FakeContext()
    loop.memory_consolidator = type(
        "NoopMemory",
        (),
        {"maybe_consolidate_by_tokens": lambda self, _session: asyncio.sleep(0)},
    )()
    saved: list[Session] = []
    loop.sessions = type("NoopSessions", (), {"save": lambda self, session: saved.append(session)})()

    async def _fake_v1_case_stream_plan(*, runtime_metadata, user_message):
        runtime_metadata["_v1_case_graded"] = True
        runtime_metadata["v1_case_graded"] = True
        runtime_metadata["score_authority"] = "rubric_scored_v1"
        runtime_metadata["grading_rubric_provenance"] = "compiled_rubric"
        runtime_metadata["case_grading_stream_mode"] = "score_first_sealed_blocks"
        runtime_metadata["presentation"] = {
            "schema_version": 1,
            "blocks": [{"type": "recap", "title": "批改结论", "summary": "命中1个，漏1个。"}],
            "fallback_text": "## 批改结论\n**得分预估：** 1 / 2 分。",
            "meta": {"streamingMode": "block_finalized"},
        }
        score_first = "## 批改结论\n**得分预估：** 1 / 2 分。\n- 命中 1 个，部分命中 0 个，漏/错 1 个。"
        blocks = [{"id": "q1", "phase": "question_detail", "sealed": True, "title": "问题1", "content": "## 问题1\n**采分点：**\n- ✅ 已命中：点1"}]
        return {
            "mode": "score_first_sealed_blocks",
            "score_first": score_first,
            "sealed_blocks": blocks,
            "final_text": score_first + "\n\n" + blocks[0]["content"],
            "presentation": runtime_metadata["presentation"],
        }

    async def _agent_loop_should_not_run(*_args, **_kwargs):
        raise AssertionError("case_grading direct V1 path must not run the generic agent LLM first")

    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_v1_case_stream_plan)
    monkeypatch.setattr(loop, "_run_agent_loop", _agent_loop_should_not_run)

    md = {"question_lifecycle_scene": "case_grading", "user_id": "qa_case"}
    session = Session(key="web:case")
    msg = InboundMessage(channel="web", sender_id="user", chat_id="case", content="【问题】1. 说明。\n回答\n作答：点1", metadata=md)
    deltas: list[str] = []
    progress: list[str] = []

    out = await loop._run_case_grading_direct(
        msg=msg,
        session=session,
        history=[],
        current_message=msg.content,
        runtime_metadata=md,
        runtime_instruction="",
        on_progress=lambda text: progress.append(text) or asyncio.sleep(0),
        on_content_delta=lambda text: deltas.append(text) or asyncio.sleep(0),
    )

    assert out is not None
    assert out.content.startswith("## 批改结论")
    assert out.metadata["v1_case_graded"] is True
    assert out.metadata["case_grading_stream_mode"] == "score_first_sealed_blocks"
    assert out.metadata["presentation"]["blocks"][0]["type"] == "recap"
    assert progress and "案例题" in progress[0]
    assert "".join(deltas).startswith("这道案例题我已经进入逐采分点批改")
    assert len(saved) >= 1
    assert session.messages[-1]["content"].startswith("## 批改结论")


@pytest.mark.asyncio
async def test_case_grading_direct_path_streams_score_first_then_sealed_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = _loop()
    loop.context = _FakeContext()
    loop.memory_consolidator = type(
        "NoopMemory",
        (),
        {"maybe_consolidate_by_tokens": lambda self, _session: asyncio.sleep(0)},
    )()
    saved: list[Session] = []
    loop.sessions = type("NoopSessions", (), {"save": lambda self, session: saved.append(session)})()

    async def _fake_v1_case_stream_plan(*, runtime_metadata, user_message):
        runtime_metadata["_v1_case_graded"] = True
        runtime_metadata["v1_case_graded"] = True
        runtime_metadata["score_authority"] = "rubric_scored_v1"
        runtime_metadata["grading_rubric_provenance"] = "compiled_rubric"
        runtime_metadata["case_grading_stream_mode"] = "score_first_sealed_blocks"
        runtime_metadata["presentation"] = {
            "schema_version": 1,
            "blocks": [{"type": "recap", "title": "批改结论", "summary": "1 / 2 分，命中1个。"}],
            "fallback_text": "## 批改结论\n**得分预估：** 1 / 2 分。",
            "meta": {"streamingMode": "block_finalized"},
        }
        score_first = "## 批改结论\n**得分预估：** 1 / 2 分。\n- 命中 1 个，部分命中 0 个，漏/错 1 个。"
        blocks = [
            {"id": "q1", "phase": "question_detail", "sealed": True, "content": "## 问题1\n**采分点：**\n- ✅ 已命中：点1"},
            {"id": "final", "phase": "final_detail", "sealed": True, "content": "## 下一步建议\n先练漏点。"},
        ]
        return {
            "mode": "score_first_sealed_blocks",
            "score_first": score_first,
            "sealed_blocks": blocks,
            "final_text": score_first + "\n\n" + "\n\n".join(block["content"] for block in blocks),
            "presentation": runtime_metadata["presentation"],
        }

    async def _legacy_final_only_should_not_run(*_args, **_kwargs):
        raise AssertionError("score-first direct path must not fall back to final-only V1 render")

    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_v1_case_stream_plan, raising=False)
    monkeypatch.setattr(loop, "_v1_case_render", _legacy_final_only_should_not_run)

    md = {"question_lifecycle_scene": "case_grading", "user_id": "qa_case"}
    session = Session(key="web:case-score-first")
    msg = InboundMessage(channel="web", sender_id="user", chat_id="case", content="【问题】1. 说明。\n回答\n作答：点1", metadata=md)
    deltas: list[str] = []
    progress: list[str] = []

    out = await loop._run_case_grading_direct(
        msg=msg,
        session=session,
        history=[],
        current_message=msg.content,
        runtime_metadata=md,
        runtime_instruction="",
        on_progress=lambda text: progress.append(text) or asyncio.sleep(0),
        on_content_delta=lambda text: deltas.append(text) or asyncio.sleep(0),
    )

    streamed = "".join(deltas)
    assert out is not None
    assert out.content.startswith("## 批改结论")
    assert out.metadata["v1_case_graded"] is True
    assert out.metadata["case_grading_stream_mode"] == "score_first_sealed_blocks"
    assert streamed.index("## 批改结论") < streamed.index("## 问题1") < streamed.index("## 下一步建议")
    assert any("已完成判分" in item for item in progress)
    assert session.messages[-1]["content"] == out.content
    assert len(saved) >= 1


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

    assert "## 批改结论" in out
    for _ in range(50):
        if fake_service.calls and md.get("personalization_context"):
            break
        await asyncio.sleep(0.01)
    assert len(fake_service.calls) == 1
    call = fake_service.calls[0]
    assert call["user_id"] == "qa_loop_v1"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "case_grading_completed"
    assert call["payload_json"]["question_node_code"] == "1A432000"
    assert call["payload_json"]["projection_taxonomy_code"] == "1A432000"
    assert md["grading_to_brain_loop"]["writeback_count"] == 1
    assert md["learning_evidence_event_id"] == "evt_v1_case_1"
    assert md["learning_training_intent"]["source"] == "grading_to_brain_loop"
    assert md["grading_to_brain_projection"]["status"] == "succeeded"
    assert md["personalization_context"]["source"] == "PersonalizationContextPack"
    assert md["next_best_action"]["source"] == "training_intent"


@pytest.mark.asyncio
async def test_v1_case_render_does_not_wait_for_personalization_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUBAN_CASE_RUBRIC_V1_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(G, "load_rubric", lambda _qid: [
        {
            "point_id": "P1",
            "text": "应编制临时用电施工组织设计",
            "score": 1.0,
            "policy": "qualitative",
            "required_terms": [],
        }
    ])

    async def _fake_batch_async(points, answer, complete_fn, api_key, *, model="deepseek-chat"):
        _ = points, answer, complete_fn, api_key, model
        return {"P1": {"status": G.MISS, "evidence_span": ""}}

    release = threading.Event()
    fake_service = _FakeLearnerStateService()

    def _slow_projection(**kwargs):
        _ = kwargs
        release.wait(timeout=1.0)

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: fake_service,
    )
    monkeypatch.setattr(AgentLoop, "_record_v1_grading_personalization", staticmethod(_slow_projection))

    md = _case_md()
    out = await asyncio.wait_for(
        _loop()._apply_v1_or_case_fallback(
            "智能体自由答复：我先不打分。", runtime_metadata=md, user_message="临时用电施工组织设计"
        ),
        timeout=0.2,
    )
    release.set()
    await asyncio.sleep(0.01)

    assert "## 批改结论" in out
    assert md["learning_evidence_event_id"] == "evt_v1_case_1"
    assert md["learning_training_intent"]["source"] == "grading_to_brain_loop"
    assert md["grading_to_brain_projection"] == {
        "status": "scheduled",
        "authority": "personalization_context_pack",
        "event_id": "evt_v1_case_1",
    }


# ---------------------------------------------------------------- Grading-to-Brain cache-first（gbrain daemon 化）


class _CacheAwareLearnerStateService(_FakeLearnerStateService):
    def __init__(self, *, cached_projection: dict | None) -> None:
        super().__init__()
        self._cached_projection = cached_projection
        self.synthesize_calls: list[dict] = []

    def read_compiled_learning_truth(self, user_id: str) -> dict:
        return dict(self._cached_projection or {})

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool = True, event_limit: int | None = None):
        self.synthesize_calls.append({"user_id": user_id, "dry_run": dry_run, "event_limit": event_limit})
        return {"projection": {"compiled_objects": []}}


def _v1_grading_event() -> dict:
    return {
        "event_type": "case_grading_completed",
        "question_id": "CASE-1",
        "awarded_score": 0,
        "max_score": 1,
        "high_risk_review": False,
        "rubric_provenance": "compiled_rubric",
        "scoring_points": [
            {
                "point_id": "P1",
                "knowledge_point": "临时用电管理",
                "hit": "miss",
                "score": 0,
                "max_score": 1,
                "mistake_type": "miss",
                "evidence_span": "",
                "policy_type": "exact_required",
            }
        ],
    }


def _cached_projection() -> dict:
    return {
        "compiled_objects": [
            {
                "object_id": "1A415000:M06",
                "object_type": "error",
                "claim_status": "confirmed",
                "concept_id": "1A415000",
                "label": "屋面与防水工程施工：近义替代",
                "supporting_event_ids": ["evt_cached"],
                "confidence": 0.9,
            }
        ],
        "weak_points": [],
    }


def test_record_v1_grading_to_brain_prefers_compiled_cache(monkeypatch) -> None:
    """gbrain daemon 化：夜间已巩固 → turn 内直接读 compiled 投影缓存，
    不再在聊天时重跑 synthesize_learning_truth。"""
    service = _CacheAwareLearnerStateService(cached_projection=_cached_projection())
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: service,
    )
    md = {"user_id": "qa_loop_v1", "session_id": "sess-1", "turn_id": "turn-1"}

    AgentLoop._record_v1_grading_to_brain(
        runtime_metadata=md,
        event=_v1_grading_event(),
        ctx={"user_answer": "作答", "question_stem": "题干", "question_id": "CASE-1"},
    )

    assert service.synthesize_calls == []
    assert md["learning_evidence_event_id"] == "evt_v1_case_1"
    assert md["personalization_context"]["top_claims"][0]["claim_id"] == "1A415000:M06"
    assert "next_best_action" in md


def test_record_v1_grading_to_brain_falls_back_to_inline_synthesis_on_cache_miss(monkeypatch) -> None:
    service = _CacheAwareLearnerStateService(cached_projection=None)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: service,
    )
    md = {"user_id": "qa_loop_v1", "session_id": "sess-1", "turn_id": "turn-1"}

    AgentLoop._record_v1_grading_to_brain(
        runtime_metadata=md,
        event=_v1_grading_event(),
        ctx={"user_answer": "作答", "question_stem": "题干", "question_id": "CASE-1"},
    )

    assert len(service.synthesize_calls) == 1
    assert service.synthesize_calls[0]["dry_run"] is True


def test_loop_grading_to_brain_is_thin_delegate_source_pin() -> None:
    """源检查钉：loop 侧只允许委托唯一 recorder seam（record_case_grading_to_brain），
    禁止重新内联 writeback/PCP 拼装逻辑——否则与练题入口形成双权威。"""
    import inspect

    src_text = inspect.getsource(AgentLoop._record_v1_grading_to_brain)
    assert "record_case_grading_to_brain" in src_text
    assert "write_case_grading_event_learning_evidence" not in src_text
    assert "build_personalization_context_pack" not in src_text


def test_case_grading_metadata_export_includes_g2b_projection_receipt() -> None:
    target = {"message_id": "msg-1"}
    AgentLoop._export_case_grading_metadata(
        {
            "question_lifecycle_scene": "case_grading",
            "v1_case_graded": True,
            "score_authority": "rubric_scored_v1",
            "grading_rubric_provenance": "on_the_fly_reference",
            "learning_evidence_event_id": "evt-1",
            "grading_to_brain_projection": {
                "status": "scheduled",
                "authority": "personalization_context_pack",
                "event_id": "evt-1",
            },
            "case_grading_adjudication_strategy": "dynamic_parallel_question_groups",
            "case_grading_adjudication_group_count": 3,
            "case_grading_adjudication_point_count": 24,
        },
        target,
    )

    assert target["message_id"] == "msg-1"
    assert target["v1_case_graded"] is True
    assert target["score_authority"] == "rubric_scored_v1"
    assert target["learning_evidence_event_id"] == "evt-1"
    assert target["grading_to_brain_projection"]["status"] == "scheduled"
    assert target["case_grading_adjudication_strategy"] == "dynamic_parallel_question_groups"
    assert target["case_grading_adjudication_group_count"] == 3
    assert target["case_grading_adjudication_point_count"] == 24


def test_case_grading_metadata_export_strips_stale_receipt_on_non_case_turn() -> None:
    target = {
        "message_id": "msg-2",
        "v1_case_graded": True,
        "score_authority": "rubric_scored_v1",
        "grading_to_brain_loop": {"writeback_count": 1},
        "learning_evidence_event_id": "evt-old",
    }

    AgentLoop._export_case_grading_metadata(
        {
            "question_lifecycle_scene": None,
            "execution_path": "tutorbot_kb_first_full_agent_policy",
            "v1_case_graded": True,
            "score_authority": "rubric_scored_v1",
            "grading_to_brain_loop": {"writeback_count": 1},
            "learning_evidence_event_id": "evt-old",
        },
        target,
    )

    assert target == {"message_id": "msg-2"}


def test_projected_exact_question_renders_authority_on_learner_surface() -> None:
    # task#10 (tutorbot capability): a bank MCQ exact_question (5% = D in the bank)
    # projected onto the learner's pasted surface (5% = A) must make the deterministic
    # exact-authority response state the answer as A — not the bank letter D — so a
    # learner who answered A (5%) is graded correct. This proves the loop's projection
    # of _prefetched_exact_question fixes the grading surface end-to-end (no LLM).
    from deeptutor.services.rag.exact_authority import build_exact_authority_response
    from deeptutor.services.rag.pipelines.supabase import SupabasePipeline

    bank = {
        "answer_kind": "mcq",
        "stem": "某工程屋面为压型金属板，设计无要求时屋面坡度最小值是（）。",
        "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
        "correct_answer": "D",
    }
    learner_query = "某工程屋面...坡度最小值是（）。A.5% B.2% C.3% D.1%。我选A"
    projected = SupabasePipeline._project_mcq_exact_question_to_query_surface(bank, learner_query)
    assert projected["correct_answer"] == "A"  # remapped to learner surface

    rendered = build_exact_authority_response(projected, user_message="我选A")
    # The authority response names A (the learner's correct letter), never D.
    assert "A" in rendered
    assert "正确答案是 D" not in rendered and "正确答案 D" not in rendered

# ── task#10: pasted-MCQ grounding projected onto the learner option surface ────
# When a learner pastes an MCQ whose option order differs from the question bank,
# the prefetch RAG grounding the grading LLM reads must be projected onto the
# learner's surface, so the prompt never carries a conflicting bank answer letter.
def test_prefetch_grounded_rag_projects_bank_grounding_to_learner_surface() -> None:
    bank_grounding = (
        "【题目】某工程屋面为压型金属板，坡度最小值是（）。\n"
        '【选项】[{"key": "A", "value": "1%"}, {"key": "B", "value": "2%"}, '
        '{"key": "C", "value": "3%"}, {"key": "D", "value": "5%"}]\n'
        "【答案】D\n【解析】压型金属板：5%。"
    )
    learner = "某工程屋面为压型金属板，坡度最小值是（）。A.5% B.2% C.3% D.1%。我选A，判对错。"

    class _RagTool:
        def preview_args(self, args):
            return args

        def consume_trace_metadata(self):
            return {}

    class _Tools:
        def get(self, name):
            return _RagTool()

        async def execute(self, name, args):
            return bank_grounding

    class _Ctx:
        def add_assistant_message(self, messages, content, **_kwargs):
            return [*messages, {"role": "assistant", "content": content}]

        def add_tool_result(self, messages, tool_call_id, name, result):
            return [*messages, {"role": "tool", "name": name, "content": result}]

    loop = _loop()
    loop.tools = _Tools()
    loop.context = _Ctx()
    loop._should_prefetch_grounded_rag = lambda **_k: True
    loop._build_rag_preview_args = lambda *_a, **_k: {"query": learner}
    loop._augment_rag_trace_metadata = lambda **_k: {}
    loop._record_rag_trace_status = lambda *_a, **_k: None

    initial = [{"role": "user", "content": learner}]
    messages = asyncio.run(
        loop._maybe_prefetch_grounded_rag(
            initial_messages=initial,
            current_message=learner,
            runtime_metadata={},
        )
    )
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "grounding tool result must be injected"
    grounding = tool_msgs[-1]["content"]
    # bank answer D rewritten to the learner's A (whose value is the correct 5%).
    assert "【答案】A" in grounding
    assert "【答案】D" not in grounding


@pytest.mark.asyncio
async def test_prefetched_rag_grounding_projects_answer_to_learner_option_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRagTool:
        def preview_args(self, params):
            return dict(params)

        def consume_trace_metadata(self):
            return {}

    class _FakeTools:
        def __init__(self) -> None:
            self.rag_tool = _FakeRagTool()

        def get(self, name):
            return self.rag_tool if name == "rag" else None

        async def execute(self, name, _args):
            assert name == "rag"
            return (
                "题库原题\n"
                "【选项】[{\"key\":\"A\",\"value\":\"1%\"},{\"key\":\"B\",\"value\":\"2%\"},"
                "{\"key\":\"C\",\"value\":\"3%\"},{\"key\":\"D\",\"value\":\"5%\"}]\n"
                "【答案】D\n"
                "【解析】屋面最小坡度：压型金属板：5%。"
            )

    loop = _loop()
    loop.tools = _FakeTools()
    loop.context = _FakeContext()
    monkeypatch.setattr(AgentLoop, "_should_prefetch_grounded_rag", classmethod(lambda cls, **_kwargs: True))

    tool_results: list[str] = []

    async def _on_tool_result(_tool_name, result, _metadata):
        tool_results.append(result)

    messages = await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "system", "content": ""}],
        current_message=(
            "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。"
            "A.5% B.1% C.2% D.3%，我选A，对吗？"
        ),
        runtime_metadata={},
        on_tool_result=_on_tool_result,
    )

    tool_message = next(item for item in messages if item["role"] == "tool")
    options_match = re.search(
        r"【选项】(?P<options>\[.*?\])\s*\n【答案】(?P<answer>[A-E])",
        tool_message["content"],
    )
    assert options_match is not None
    assert options_match.group("answer") == "A"
    options = json.loads(options_match.group("options"))
    assert options[0] == {"key": "A", "value": "5%"}
    assert "【答案】D" not in tool_message["content"]
    assert tool_results == [tool_message["content"]]


# ---------------------------------------------------------------------------
# tier1/2 可达性收复 批1a（2026-07-30 指挥官阶段1）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_grading_direct_prefetches_exact_before_v1(tmp_path, monkeypatch) -> None:
    """直批此前先于 prefetch 执行 → 粘贴库内题 eq 恒缺、恒 tier3。收复后：
    直批入口先跑既有 prefetch（匹配权威不变），V1 计划能看到 _prefetched_exact_question。"""
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class _P(LLMProvider):
        async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                       temperature=0.7, reasoning_effort=None, tool_choice=None,
                       on_content_delta=None):
            return LLMResponse(content="占位")

        def get_default_model(self):
            return "fake"

    loop = AgentLoop(
        bus=MessageBus(), provider=_P(), workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    calls = {"prefetch": 0, "plan_saw_eq": None}

    async def _fake_prefetch(*, initial_messages, current_message, runtime_metadata, **kw):
        calls["prefetch"] += 1
        runtime_metadata["_prefetched_exact_question"] = {
            "answer_kind": "case_study", "question_id": 9348,
            "source_chunk_id": "EXAM_1A430000_P0014_06", "exam_year": 2024,
        }
        return initial_messages

    async def _fake_plan(*, runtime_metadata, user_message):
        calls["plan_saw_eq"] = isinstance(
            runtime_metadata.get("_prefetched_exact_question"), dict
        )
        return {"final_text": "## 批改\n占位判分正文", "score_first": "占位"}

    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _fake_prefetch)
    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_plan)
    monkeypatch.setattr(loop, "_is_case_grading_scene", lambda md: True)
    # 本测试聚焦管道时序（prefetch 先于 V1）；门策略另有专测，这里放行。
    monkeypatch.setattr(
        AgentLoop, "_should_prefetch_grounded_rag",
        classmethod(lambda cls, **kw: True),
    )

    from deeptutor.tutorbot.bus.events import InboundMessage
    msg = InboundMessage(channel="test", sender_id="u", chat_id="c", content="题干…\n作答…")
    # 1b admission：直批取回权威只看 kb 在场（不再受聊天门管辖）。
    md_ref = {"question_lifecycle_scene": "case_grading", "default_kb": "construction-exam"}
    out = await loop._run_case_grading_direct(
        msg=msg, session=SimpleNamespace(metadata={}, key="k", messages=[], last_consolidated=0),
        history=[], current_message="【题目】某工程…\n【我的作答】…",
        runtime_metadata=md_ref,
        runtime_instruction="",
    )

    assert calls["prefetch"] == 1
    assert calls["plan_saw_eq"] is True
    # 门必须发声（1b 仪器）：allowed 且命中 eq → marker=allowed。
    assert str(md_ref.get("case_grading_prefetch_gate") or "").startswith("allowed")


@pytest.mark.asyncio
async def test_grounded_prefetch_is_idempotent_per_turn(tmp_path, monkeypatch) -> None:
    """幂等闸：直批已 prefetch 后 fell_through 到外层，同 turn 不得二次检索。"""
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class _P(LLMProvider):
        async def chat(self, *a, **k):
            return LLMResponse(content="x")

        def get_default_model(self):
            return "fake"

    loop = AgentLoop(
        bus=MessageBus(), provider=_P(), workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )
    md = {"_grounded_rag_prefetch_done": True}
    executed = {"rag": 0}

    class _Boom:
        def preview_args(self, a):
            executed["rag"] += 1
            return a

    monkeypatch.setattr(loop.tools, "get", lambda name: _Boom())
    out = await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "q"}],
        current_message="q", runtime_metadata=md,
    )
    assert executed["rag"] == 0  # 幂等：直接短路，未触检索


# ---------------------------------------------------------------------------
# tier1/2 可达性收复 批1b（2026-07-30 指挥官修正令：门+A3+复合qid观测+成功侧导出同批）
# ---------------------------------------------------------------------------
def _direct_loop(tmp_path):
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class _P(LLMProvider):
        async def chat(self, *a, **k):
            return LLMResponse(content="占位")

        def get_default_model(self):
            return "fake"

    return AgentLoop(
        bus=MessageBus(), provider=_P(), workspace=tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda key: SimpleNamespace(metadata={}, key=key),
            save=lambda session: None,
        ),
    )


async def _run_direct(loop, md_ref, monkeypatch, *, plan=None):
    from deeptutor.tutorbot.bus.events import InboundMessage

    calls = {"prefetch": 0}

    async def _fake_prefetch(*, initial_messages, current_message, runtime_metadata, **kw):
        calls["prefetch"] += 1
        return initial_messages

    async def _fake_plan(*, runtime_metadata, user_message):
        return plan

    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _fake_prefetch)
    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_plan)
    monkeypatch.setattr(loop, "_is_case_grading_scene", lambda md: True)
    msg = InboundMessage(channel="test", sender_id="u", chat_id="c", content="题干…\n作答…")
    await loop._run_case_grading_direct(
        msg=msg, session=SimpleNamespace(metadata={}, key="k", messages=[], last_consolidated=0),
        history=[], current_message="【题目】某工程基坑深6米…问题1：指出不妥之处。\n【我的作答】深度超5米应专家论证。",
        runtime_metadata=md_ref, runtime_instruction="",
    )
    return calls


@pytest.mark.asyncio
async def test_direct_admission_ignores_chat_gate_veto(tmp_path, monkeypatch) -> None:
    """死锁回归（live 实证 denied:decision）：权威空壳 active_object（键在值空）曾触发
    通用聊天门禁检索——「没权威→禁取权威」。1b 收权后：直批 admission 只看 kb 在场，
    聊天门（此处保持真实实现，会拒）无否决权。"""
    md_ref = {
        "question_lifecycle_scene": "case_grading",
        "knowledge_bases": ["construction-exam"],
        # 生产实况复刻：无 default_tools + 空壳 active_object（question_id/correct_answer 全空）
        "active_object": {
            "object_type": "single_question",
            "state_snapshot": {"question": "某工程基坑…", "question_id": "", "correct_answer": None,
                               "user_answer": ""},
        },
    }
    calls = await _run_direct(_direct_loop(tmp_path), md_ref, monkeypatch)
    assert calls["prefetch"] == 1
    assert md_ref.get("case_grading_prefetch_gate") == "allowed_no_exact_hit"


@pytest.mark.asyncio
async def test_direct_admission_no_kb_denies_with_voice(tmp_path, monkeypatch) -> None:
    md_ref = {"question_lifecycle_scene": "case_grading"}
    calls = await _run_direct(_direct_loop(tmp_path), md_ref, monkeypatch)
    assert calls["prefetch"] == 0
    assert md_ref.get("case_grading_prefetch_gate") == "denied:no_default_kb"


@pytest.mark.asyncio
async def test_direct_admission_authority_present_skips_fetch(tmp_path, monkeypatch) -> None:
    md_ref = {
        "question_lifecycle_scene": "case_grading",
        "default_kb": "construction-exam",
        "exact_question": {
            "answer_kind": "case_study",
            "correct_answer": "开挖深度超过5m（含）应组织专家论证。",
        },
    }
    calls = await _run_direct(_direct_loop(tmp_path), md_ref, monkeypatch)
    assert calls["prefetch"] == 0
    assert md_ref.get("case_grading_prefetch_gate") == "authority_already_present"


def test_case_stem_numeric_variant_gate() -> None:
    """改数变体闸：同单位、值不同、且用户值不在题库题任何数字中 → 判变体；
    子集粘贴（用户数字 ⊆ 题库数字）永不触发。"""
    eq = {
        "stem": "某基坑开挖深度6米，合同价3000万元。",
        "covered_subquestions": [{"prompt": "问题1：指出不妥之处？", "question": ""}],
    }
    # 改数变体：6米 → 8米
    assert AgentLoop._case_stem_numeric_variant(eq, "某基坑开挖深度8米，问题1：指出不妥之处？") is True
    # 同题原数：不触发
    assert AgentLoop._case_stem_numeric_variant(eq, "某基坑开挖深度6米，问题1：指出不妥之处？") is False
    # 子集粘贴（只提金额）：不触发
    assert AgentLoop._case_stem_numeric_variant(eq, "合同价3000万元的工程，问题1？") is False
    # 题库无带单位数字：闸不表态
    assert AgentLoop._case_stem_numeric_variant({"stem": "论述质量管理要点。"}, "深度8米") is False


def test_build_ctx_numeric_variant_demotes_eq() -> None:
    """真实威胁形状：小问文字与题库题完全一致（锚定匹配放行），但背景资料数字被改
    （6米→8米）。2-gram/锚定匹配对此无鉴别力，数字变体闸必须兜底撤销 eq——
    否则官方 rubric 会去判一道数值语义已变的题。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "stem": "【背景资料】某基坑开挖深度6米。",
            "covered_subquestions": [
                {"question": "【问题1】指出土方开挖中的不妥之处？",
                 "authoritative_answer": "应专家论证", "display_index": "1"},
            ],
        },
    }
    ctx = AgentLoop._build_v1_case_ctx(
        md,
        "【背景资料】某基坑开挖深度8米。【问题1】指出土方开挖中的不妥之处？\n我的答案：需要论证。",
    )
    assert md.get("exact_question_blocked_reason") == "case_numeric_variant"
    assert ctx["correct_answer"] == ""  # eq 已撤，参考答案不得泄入


def test_build_ctx_composite_qid_candidate_observe_only() -> None:
    """复合 qid【观测不武装】：唯一性审计实证运行时 display_index(1基) 与编译期
    En(0基) 无共享权威（模拟命中 23/354 全部错绑）——候选键只导出 marker，
    绝不进 ctx.question_id 喂 load_rubric。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "question_id": 9348,
            "source_chunk_id": "EXAM_1A430000_P0014_06",
            "exam_year": 2024,
            "stem": "【背景资料】某工程基坑开挖深度6米。",
            "covered_subquestions": [
                {"prompt": "【问题1】指出土方开挖中的不妥之处？",
                 "authoritative_answer": "开挖深度超过5m（含）应组织专家论证。",
                 "display_index": "1"},
                {"prompt": "【问题2】说明正确做法？",
                 "authoritative_answer": "应编制专项施工方案。",
                 "display_index": "2"},
            ],
        },
    }
    ctx = AgentLoop._build_v1_case_ctx(
        md,
        "【背景资料】某工程基坑开挖深度6米。【问题1】指出土方开挖中的不妥之处？\n我的答案：深度超5米应专家论证。",
    )
    assert md.get("case_grading_composite_qid_candidate") == "2024::EXAM_1A430000_P0014_06::E1"
    assert ctx["question_id"] == "9348"  # 不武装：仍是 bank 整数 id，永不命中 pgo 键


@pytest.mark.asyncio
async def test_outer_seam_reentry_only_on_authority_upgrade(tmp_path, monkeypatch) -> None:
    """单发闸窄豁免：fell_through 后仅当 qid 客观升级（空→有）才放行一次再入，
    升级也发声（case_grading_outer_seam_reentry marker）。"""
    loop = _direct_loop(tmp_path)
    # 目录级既往病免疫：别处测试会把模块 logger 换成缺方法的 SimpleNamespace。
    import deeptutor.tutorbot.agent.loop as _loop_mod
    monkeypatch.setattr(
        _loop_mod, "logger",
        SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None,
                        warning=lambda *a, **k: None, error=lambda *a, **k: None),
    )

    # (a) qid 未升级 → 维持关闭
    md_a = {"case_grading_direct_fell_through": True, "case_grading_direct_attempt_qid": ""}
    monkeypatch.setattr(loop, "_build_v1_case_ctx", lambda md, um: {"question_id": ""})
    assert await loop._v1_case_stream_plan(runtime_metadata=md_a, user_message="q") is None
    assert "case_grading_outer_seam_reentry" not in md_a

    # (b) qid 升级 → 放行一次并发声（scene 置非 case_grading 让其随即返回，
    # marker 在场即证明已越过单发闸）
    md_b = {
        "case_grading_direct_fell_through": True,
        "case_grading_direct_attempt_qid": "",
        "question_lifecycle_scene": "mcq_grading",
    }
    monkeypatch.setattr(loop, "_build_v1_case_ctx", lambda md, um: {"question_id": "9348"})
    assert await loop._v1_case_stream_plan(runtime_metadata=md_b, user_message="q") is None
    assert md_b.get("case_grading_outer_seam_reentry") == "authority_upgraded"

    # (c) 已再入过 → 不得二次放行
    md_c = dict(md_b)
    assert await loop._v1_case_stream_plan(runtime_metadata=md_c, user_message="q") is None


def test_case_grading_new_markers_projected_per_turn() -> None:
    """观测对称律：新 marker 必须在 CASE_GRADING_TURN_METADATA_KEYS 里随每跳导出。"""
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_GRADING_TURN_METADATA_KEYS,
        copy_current_case_grading_turn_metadata,
    )

    for key in (
        "case_grading_prefetch_gate",
        "case_grading_direct_attempt_qid",
        "case_grading_composite_qid_candidate",
        "case_grading_outer_seam_reentry",
        "case_rubric_score_total_mismatch",
    ):
        assert key in CASE_GRADING_TURN_METADATA_KEYS, key
    # 通用 marker 不得入 case 元组（strip 会在非 case 轮剥掉别的路径写的值）
    assert "exact_question_blocked_reason" not in CASE_GRADING_TURN_METADATA_KEYS
    assert "case_reference_blocked_reason" not in CASE_GRADING_TURN_METADATA_KEYS

    source = {
        "question_lifecycle_scene": "case_grading",
        "case_grading_prefetch_gate": "allowed",
        "case_grading_composite_qid_candidate": "2024::EXAM_X::E1",
    }
    target: dict = {}
    copy_current_case_grading_turn_metadata(source, target)
    assert target["case_grading_prefetch_gate"] == "allowed"
    assert target["case_grading_composite_qid_candidate"] == "2024::EXAM_X::E1"


@pytest.mark.asyncio
async def test_prefetch_tool_query_override_and_empty_exact_honesty(tmp_path, monkeypatch) -> None:
    """1b live 实证双修：①直批身份检索只喂题干（作答噪声污染 shape 分类与匹配）；
    ②pipeline 未命中时 trace 元数据带 exact_question: {}，空壳不得写入
    _prefetched_exact_question 冒充命中（marker 必须落 allowed_no_exact_hit）。"""
    loop = _direct_loop(tmp_path)
    seen = {"query": None}

    class _FakeRagTool:
        def preview_args(self, params):
            seen["query"] = params.get("query")
            return dict(params)

        def consume_trace_metadata(self):
            return {"exact_question": {}}  # pipeline 未命中的真实形状

    class _FakeTools:
        def get(self, name):
            return _FakeRagTool() if name == "rag" else None

        async def execute(self, name, _args):
            return "无命中的普通检索文本"

    loop.tools = _FakeTools()

    class _Ctx:
        def add_assistant_message(self, messages, content, **_k):
            return [*messages, {"role": "assistant", "content": content}]

        def add_tool_result(self, messages, tool_call_id, name, result):
            return [*messages, {"role": "tool", "name": name, "content": result}]

    loop.context = _Ctx()
    monkeypatch.setattr(loop, "_augment_rag_trace_metadata",
                        lambda **k: dict((k.get("tool_trace_metadata") or {})))
    monkeypatch.setattr(loop, "_record_rag_trace_status", lambda *a, **k: None)

    md = {}
    await loop._maybe_prefetch_grounded_rag(
        initial_messages=[{"role": "user", "content": "全文"}],
        current_message="【背景资料】题干…【问题】1. …\n我的答案：作答…",
        runtime_metadata=md,
        force_authority_fetch=True,
        tool_query_override="【背景资料】题干…【问题】1. …",
    )
    # ① 检索 query 被题干覆写（不含作答）
    assert seen["query"] == "【背景资料】题干…【问题】1. …"
    # ② 空壳 exact 不得入场
    assert "_prefetched_exact_question" not in md


def test_build_ctx_exports_user_stem_for_coverage() -> None:
    """覆盖对账基准（live 实证）：exact 命中单小问兄弟行时 eq.stem 只含 1 问，
    ctx 必须另携学生所见整题面 user_stem 供覆盖对账。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "stem": "【背景资料】某工程。【问题1】指出不妥之处？",  # 单小问行
            "covered_subquestions": [
                {"prompt": "【问题1】指出不妥之处？", "authoritative_answer": "答案", "display_index": "1"},
            ],
        },
    }
    user_paste = (
        "【背景资料】某工程。【问题1】指出不妥之处？【问题2】写出名称？"
        "【问题3】构造名称？【问题4】工艺流程？\n我的答案：只答问题1。"
    )
    ctx = AgentLoop._build_v1_case_ctx(md, user_paste)
    assert "问题4" in ctx["user_stem"]          # 整题面在
    assert "问题4" not in ctx["question_stem"]  # eq.stem 只有 1 问（判分接地不变）


def test_build_ctx_fail_closed_when_stem_unsplittable() -> None:
    """OD-002 fail-closed 保底闸：疑似案例投稿但作答切割失败（user_stem 空）时，
    题库参考答案不得入判——核验面缺失宁降 tier3，不许拿别人家钥匙倒诬。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "stem": "【背景资料】另一道题的题干。",
            "correct_answer": "别人家的答案钥匙",
            "covered_subquestions": [
                {"prompt": "【问题1】？", "authoritative_answer": "别人家的答案", "display_index": "1"},
            ],
        },
    }
    # 无任何可识别作答标记的长案例形状文本 → split 失败 → user_stem 空
    weird = "【背景资料】某工程质量问题描述很长" + "内容" * 60 + "\n【问题】相关小问混排无标记作答内容混在一起"
    ctx = AgentLoop._build_v1_case_ctx(md, weird)
    assert md.get("exact_question_blocked_reason") == "unverifiable_submission_shape"
    assert ctx["correct_answer"] == ""  # 钥匙没入判


def test_toolless_repair_messages_strip_tool_shape() -> None:
    """OD-003 根治：修复轮消息必须剥掉工具形态（tool_calls 壳+tool 角色），
    证据展平为文本——模型没有可模仿的工具语法，才不会继续吐 tool_calls。"""
    messages = [
        {"role": "system", "content": "你是助教"},
        {"role": "user", "content": "【背景资料】某工程…\n【问题】1. 指出不妥？"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "rag"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "rag", "content": "检索证据A"},
        {"role": "assistant", "content": "草稿片段", "tool_calls": [{"id": "c2", "function": {"name": "rag"}}]},
        {"role": "tool", "tool_call_id": "c2", "name": "rag", "content": "检索证据B"},
    ]
    out = AgentLoop._toolless_repair_messages(messages, repair_prompt="请直接作答")
    assert all("tool_calls" not in m for m in out)
    assert all(m.get("role") != "tool" for m in out)
    joined = "\n".join(str(m.get("content") or "") for m in out)
    assert "检索证据A" in joined and "检索证据B" in joined   # 证据不丢
    assert "【问题】1. 指出不妥？" in joined                  # 题面在
    assert out[-1]["content"] == "请直接作答"                 # 修复指令末位
    assert "草稿片段" in joined                               # 草稿保留供参考


def test_toolless_repair_truncates_huge_evidence() -> None:
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    messages += [{"role": "tool", "tool_call_id": f"c{i}", "name": "rag", "content": "证" * 3000}
                 for i in range(5)]
    out = AgentLoop._toolless_repair_messages(messages, repair_prompt="p", max_evidence_chars=1000)
    ev = next(m for m in out if "已检索到的全部证据" in str(m.get("content") or ""))
    assert len(ev["content"]) < 1400 and "证据已截断" in ev["content"]


def test_build_ctx_stem_fallback_when_scene_jitter_drops_case_context() -> None:
    """OD-004 补刀：scene 抖动（LLM 参与）导致 eq/fc/split 全空时，判分不得因
    题面缺位整条降级——学生已交案例作答=判分行为在场，题面兜底取其原文
    （tier3 从学生自己贴的题面推导，不涉他题钥匙，无倒诬风险）。"""
    md = {}
    raw = ("【背景资料】某工程施工中出现质量问题需要整改" + "详细描述" * 30 +
           "\n【问题】1. 指出不妥？2. 正确做法？\n以上是我的理解，请批改。")
    ctx = AgentLoop._build_v1_case_ctx(md, raw)
    assert ctx["question_stem"], "题面不得为空（否则 no_reference 整条降级）"
    assert md.get("case_stem_fallback") == "raw_submission"
    # 短文本/非案例形状不兜底（不制造假判分面）
    md2 = {}
    ctx2 = AgentLoop._build_v1_case_ctx(md2, "这题怎么做？")
    assert "case_stem_fallback" not in md2


def test_case_stem_fallback_marker_projected_from_event() -> None:
    """OD-004 根治配套（[luban_grading_engine] domain test）：共享判分核落的
    case_stem_fallback 必须经 tutorbot 事件→md 映射上全 sink（兜底生效可观测）。"""
    from deeptutor.services.construction_grading.case_output_policy import (
        CASE_GRADING_AUTHORITY_EXPORT_KEYS,
        copy_current_case_grading_turn_metadata,
    )

    assert "case_stem_fallback" in CASE_GRADING_AUTHORITY_EXPORT_KEYS
    source = {
        "question_lifecycle_scene": "case_grading",
        "case_stem_fallback": "submission_text",
        "score_authority": "rubric_scored_v1_diagnostic",
    }
    target: dict = {}
    copy_current_case_grading_turn_metadata(source, target)
    assert target["case_stem_fallback"] == "submission_text"


def test_build_ctx_exports_reference_coverage_counts() -> None:
    """P0 兜底满分根治（[luban_grading_engine] domain test）：ctx 必须携带确定性
    覆盖计数——参考答案覆盖的小问数（来自 supabase covered_indexes，此前零消费者）
    与学生题面小问总数，供判分核按比例缩放分母。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            # 兄弟行的真实形状：stem 就是那一个小问（与用户题面中该问逐字一致）
            "stem": "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？",
            "covered_indexes": ["1"],          # 兄弟行：只覆盖问题1
            "covered_subquestions": [
                {"prompt": "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？",
                 "authoritative_answer": "官方答案1",
                 "display_index": "1"},
            ],
        },
    }
    paste = ("【背景资料】某工程施工出现问题。\n"
             "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？\n"
             "问题2：写出质量缺陷名称？\n问题3：写出防水构造层名称？\n"
             "问题4：补充治理工艺流程？\n我的答案：只答了问题1。")
    ctx = AgentLoop._build_v1_case_ctx(md, paste)
    assert ctx["case_reference_covered_count"] == 1
    assert ctx["case_stem_subquestion_count"] == 4


def test_coverage_numerator_uses_adopted_subquestions_not_row_count() -> None:
    """P0-b（2026-08-01 live 实证）：覆盖分子必须是"参考答案实际采纳了几个小问"，
    不是"检索回来几行兄弟行"——payload 报 4 行但按用户题面过滤后只采纳 1 问时，
    分子必须是 1（旧行为算 4 → 1/4 的作答拿到 8/10）。"""
    md = {
        "_prefetched_exact_question": {
            "answer_kind": "case_study",
            "stem": "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？",
            "covered_indexes": ["1", "2", "3", "4"],      # payload 说覆盖 4 个
            "covered_subquestions": [
                {"prompt": "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？",
                 "authoritative_answer": "官方答案1", "display_index": "1"},
                {"prompt": "问题2：写出完全不同主题的另一个小问内容？",
                 "authoritative_answer": "官方答案2", "display_index": "2"},
                {"prompt": "问题3：再一个不相关的小问内容描述？",
                 "authoritative_answer": "官方答案3", "display_index": "3"},
                {"prompt": "问题4：第四个不相关的小问内容描述？",
                 "authoritative_answer": "官方答案4", "display_index": "4"},
            ],
        },
    }
    md["_prefetched_exact_question"]["correct_answer"] = "官方答案1"
    # 学生贴了整题 4 问，但参考只采纳了与题面匹配的问题1
    paste = ("【背景资料】某工程施工出现问题需要整改说明。\n"
             "问题1：指出工程施工质量检测管理中的不妥之处并说明正确做法？\n"
             "问题2：写出质量缺陷名称有哪些内容？\n"
             "问题3：写出防水构造层的名称？\n"
             "问题4：补充完整治理工艺流程？\n"
             "我的答案：我认为试验员记录不妥。")
    ctx = AgentLoop._build_v1_case_ctx(md, paste)
    assert ctx["case_reference_covered_count"] == 1, (
        f"分子应为实际采纳的 1 个小问，实得 {ctx['case_reference_covered_count']}"
    )
    assert ctx["case_stem_subquestion_count"] == 4
