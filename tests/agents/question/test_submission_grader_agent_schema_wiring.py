"""
plan §Phase 4 Step 4.2 / Batch D.2 Gap 4 — SubmissionGraderAgent 接 schema。

测试通过 monkeypatch stream_llm 验证：
  * 缺段时触发 self-repair（第二次 stream_llm 调用）。
  * 第二次 stream 仍缺时模板兜底（apply_fallback_templates）。
  * ``explanation_section_miss`` 写入调用方提供的 trace_collector。
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from deeptutor.agents.question.agents.submission_grader_agent import SubmissionGraderAgent


_FULL_EXPLANATION = """\
### 阅卷结论
本题答错。

### 正确答案
B 选项。

### 为什么错
你忽略了关键采分点。

### 知识点
建设工程安全管理。

### 易错点
把行政法规与部门规章混淆。

### 记忆口诀
"先论后审，谁论谁审"。

### 下一步
继续做 3 道同考点变式题。

### 逐项解析
A：错；B：对；C：错；D：错。
"""

_PARTIAL_EXPLANATION = """\
### 阅卷结论
本题答错。

### 正确答案
B 选项。
"""


def _make_agent(monkeypatch: pytest.MonkeyPatch, *, stream_outputs: list[str]) -> SubmissionGraderAgent:
    """Bypass BaseAgent.__init__ (which loads LLM config) and patch stream_llm."""

    agent = SubmissionGraderAgent.__new__(SubmissionGraderAgent)
    agent.language = "zh"  # type: ignore[attr-defined]
    # Stub minimal BaseAgent surface.
    agent.get_prompt = lambda key, default: ""  # type: ignore[attr-defined]
    output_iter = iter(stream_outputs)

    async def fake_stream_llm(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        try:
            text = next(output_iter)
        except StopIteration:
            text = ""
        # yield the full text in one chunk; agent concatenates internally.
        yield text

    agent.stream_llm = fake_stream_llm  # type: ignore[attr-defined]
    return agent


def test_grader_writes_section_miss_when_first_llm_passes_all_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent(monkeypatch, stream_outputs=[_FULL_EXPLANATION])
    trace_collector: dict[str, Any] = {}
    explanation = asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={
                "question_id": "q_1",
                "question_type": "choice",
                "is_correct": False,
                "question": "...",
            },
            trace_collector=trace_collector,
        )
    )
    assert "B 选项" in explanation
    assert trace_collector["explanation_section_miss"] == []
    assert "verdict" in trace_collector["explanation_sections"]
    assert "option_analysis" in trace_collector["explanation_sections"]


def test_grader_triggers_self_repair_when_first_llm_misses_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repair_supplement = (
        "### 为什么错\n你忽略了关键采分点。\n"
        "### 知识点\n建设工程安全管理。\n"
        "### 易错点\n把行政法规与部门规章混淆。\n"
        "### 记忆口诀\n先论后审。\n"
        "### 下一步\n做 3 道同考点题。\n"
        "### 逐项解析\nA错 B对 C错 D错。\n"
    )
    agent = _make_agent(monkeypatch, stream_outputs=[_PARTIAL_EXPLANATION, repair_supplement])
    trace_collector: dict[str, Any] = {}
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={
                "question_id": "q_2",
                "question_type": "choice",
                "is_correct": False,
                "question": "...",
            },
            trace_collector=trace_collector,
        )
    )
    # process 返回首轮 raw markdown；修复后的 sections 通过 trace_collector 暴露给 capability.
    sections = trace_collector["explanation_sections"]
    assert sections.get("why_wrong"), "self-repair must fill why_wrong"
    assert sections.get("knowledge_point"), "self-repair must fill knowledge_point"
    miss = trace_collector["explanation_section_miss"]
    assert "verdict" not in miss
    assert "knowledge_point" not in miss


def test_grader_falls_back_to_template_when_repair_still_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 两次 LLM 都只给阅卷结论；剩下段必须由模板兜底
    only_verdict = "### 阅卷结论\n本题答错。"
    agent = _make_agent(monkeypatch, stream_outputs=[only_verdict, only_verdict])
    trace_collector: dict[str, Any] = {}
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={
                "question_id": "q_3",
                "question_type": "choice",
                "is_correct": False,
                "question": "...",
            },
            trace_collector=trace_collector,
        )
    )
    sections = trace_collector["explanation_sections"]
    # 模板填充：所有 required keys 都应有内容
    for key in ("verdict", "correct_answer", "why_wrong", "knowledge_point", "common_pitfall", "mnemonic", "next_practice"):
        assert sections.get(key), f"{key} should be filled by template fallback"
    # explanation_section_miss 应记录原始缺段名单（template 填充不修改 miss list）
    assert len(trace_collector["explanation_section_miss"]) > 0
