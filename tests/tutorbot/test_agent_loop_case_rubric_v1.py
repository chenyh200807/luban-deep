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


@pytest.mark.asyncio
async def test_agent_loop_honors_mode_execution_policy_max_tool_rounds(tmp_path) -> None:
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry as TutorBotToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class LoopingProvider(LLMProvider):
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
                content="继续调用工具",
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

    provider = LoopingProvider()
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
    metadata = {
        "default_tools": ["rag"],
        "mode_execution_policy": {"max_tool_rounds": 2},
    }

    final_content, tools_used, _messages = await loop._run_agent_loop(
        [{"role": "user", "content": "一直调用工具"}],
        runtime_metadata=metadata,
    )

    assert provider.calls == 2
    assert tools_used == ["rag", "rag"]
    assert tool.calls == [{"topic": "round-1"}, {"topic": "round-2"}]
    assert metadata["effective_max_tool_rounds"] == 2
    assert "maximum number of tool call iterations (2)" in (final_content or "")


def test_build_v1_case_ctx_extracts_reference_from_covered_subquestions() -> None:
    ctx = AgentLoop._build_v1_case_ctx(_case_md(), "我的作答：共用一个开关箱不妥")
    assert ctx["question_id"] == "CASE-1"
    assert ctx["construction_grading_result"]["type"] == "case"
    # reference comes from covered_subquestions[].authoritative_answer (NOT top-level correct_answer)
    assert "共用一个开关箱" in ctx["correct_answer"]
    assert "应编制临时用电施工组织设计" in ctx["correct_answer"]
    assert ctx["user_answer"].startswith("我的作答")
    assert ctx["node_code"] == "1A432000"


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

    async def _fake_derive(stem, complete_fn, api_key, *, model="deepseek-chat", provider_authority=""):
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
