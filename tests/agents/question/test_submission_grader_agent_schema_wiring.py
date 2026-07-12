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
    """Bypass BaseAgent.__init__ (which loads LLM config) and patch stream_llm.

    记录每次 stream_llm 的 kwargs 到 ``agent.stream_calls``（Battle2 S2-T2：
    断言 repair 触发次数与 max_tokens cap 联动）。
    """

    agent = SubmissionGraderAgent.__new__(SubmissionGraderAgent)
    agent.language = "zh"  # type: ignore[attr-defined]
    # Stub minimal BaseAgent surface.
    agent.get_prompt = lambda key, default: ""  # type: ignore[attr-defined]
    agent.get_max_tokens = lambda: 4096  # type: ignore[attr-defined]
    agent.stream_calls = []  # type: ignore[attr-defined]
    # 缺省钉死 flag off（宿主 .env 不得影响测试）；flag-on 用例再显式覆盖。
    _force_flag(monkeypatch, False)
    output_iter = iter(stream_outputs)

    async def fake_stream_llm(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        agent.stream_calls.append(dict(kwargs))
        try:
            text = next(output_iter)
        except StopIteration:
            text = ""
        # yield the full text in one chunk; agent concatenates internally.
        yield text

    agent.stream_llm = fake_stream_llm  # type: ignore[attr-defined]
    return agent


_COMPACT_EXPLANATION = """\
### 阅卷结论
本题答错，你答了 A、正确答案是 B。

### 正确答案
B（按顺序关闭）。依据防火门规范要求，考点：防火门关闭方式。

### 为什么错
把顺序器保证的顺序关闭理解成了自动关闭，属概念混淆。

### 下一步
现在把"双扇防火门按顺序关闭"抄 1 遍。

### 逐项解析
你选的 A 错：双扇门须分先后；B 正确：顺序器保证按顺序关闭；C/D 均不符合规范表述。
"""


def test_grader_compact_shape_without_optional_sections_skips_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Battle2 S2-T1：新 compact 形状（缺易错点/口诀/知识点）不算缺段、不触发第二次全量 LLM。"""
    agent = _make_agent(monkeypatch, stream_outputs=[_COMPACT_EXPLANATION])
    trace_collector: dict[str, Any] = {}
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={
                "question_id": "q_compact",
                "question_type": "choice",
                "is_correct": False,
                "question": "...",
            },
            trace_collector=trace_collector,
        )
    )
    assert len(agent.stream_calls) == 1, "optional sections missing must NOT trigger self-repair"
    assert trace_collector["explanation_section_miss"] == []
    sections = trace_collector["explanation_sections"]
    for key in ("verdict", "correct_answer", "why_wrong", "next_practice", "option_analysis"):
        assert sections.get(key)
    for key in ("knowledge_point", "common_pitfall", "mnemonic"):
        assert key not in sections


def _force_flag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """钉死 compact 灰度旗标（env_store 读磁盘 .env，monkeypatch.setenv 不可靠——直接补丁模块内引用）。"""
    import deeptutor.agents.question.agents.submission_grader_agent as agent_module

    monkeypatch.setattr(
        agent_module, "env_flag", lambda name, *, default=False: value if name == "DEEPTUTOR_MCQ_FEEDBACK_COMPACT" else default
    )


def test_flag_off_keeps_legacy_prompt_and_no_max_tokens_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Battle2 S2-T2 指挥官改判：flag off 臂 prompt 与 token 顶都必须与现状 bit-for-bit 一致。"""
    agent = _make_agent(monkeypatch, stream_outputs=[_FULL_EXPLANATION])
    _force_flag(monkeypatch, False)
    requested_keys: list[str] = []
    agent.get_prompt = lambda key, default="": (requested_keys.append(key), "")[1]  # type: ignore[attr-defined]
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={"question_id": "q_off", "question_type": "choice", "is_correct": False, "question": "..."},
            trace_collector={},
        )
    )
    assert "system_compact" not in requested_keys
    assert "grade_submission_compact" not in requested_keys
    assert agent.stream_calls, "stream_llm must be called"
    for call in agent.stream_calls:
        assert call.get("max_tokens") is None, "flag off must NOT cap max_tokens (keeps config 4096)"


def test_flag_on_selects_compact_prompt_and_caps_single_question_at_1400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _make_agent(monkeypatch, stream_outputs=[_COMPACT_EXPLANATION])
    _force_flag(monkeypatch, True)
    requested_keys: list[str] = []
    agent.get_prompt = lambda key, default="": (requested_keys.append(key), "")[1]  # type: ignore[attr-defined]
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={"question_id": "q_on", "question_type": "choice", "is_correct": False, "question": "..."},
            trace_collector={},
        )
    )
    assert "system_compact" in requested_keys
    assert "grade_submission_compact" in requested_keys
    assert len(agent.stream_calls) == 1
    assert agent.stream_calls[0].get("max_tokens") == 1400


def test_flag_on_batch_items_widen_cap_linearly(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(monkeypatch, stream_outputs=[_COMPACT_EXPLANATION])
    _force_flag(monkeypatch, True)
    items = [
        {"question_id": f"q_{i}", "question_type": "choice", "is_correct": False, "question": "..."}
        for i in range(4)
    ]
    asyncio.run(
        agent.process(
            user_message="1A 2B 3C 4D",
            question_context={
                "question_id": "q_batch",
                "question_type": "choice",
                "is_correct": False,
                "question": "...",
                "items": items,
            },
            trace_collector={},
        )
    )
    # 4 题：1400 + 600*3 = 3200（≤ 配置 4096 不截顶）
    assert agent.stream_calls[0].get("max_tokens") == 3200


def test_flag_on_truncated_stream_repairs_with_same_cap_and_fallback_fills_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模拟 finish_reason=length 截断在逐项解析中途：repair 同 cap；两轮仍缺 → 模板兜底，
    4 必备段全部非空（硬约束40：判分轮永不空段），miss 名单如实记录。"""
    truncated = "### 阅卷结论\n本题答错，你答了 A、正确答案是 B。\n\n### 正确答案\nB（按顺序关闭）。\n\n### 逐项解析\n你选的 A 错：双扇门须"
    agent = _make_agent(monkeypatch, stream_outputs=[truncated, ""])
    _force_flag(monkeypatch, True)
    trace_collector: dict[str, Any] = {}
    asyncio.run(
        agent.process(
            user_message="我选 A",
            question_context={"question_id": "q_trunc", "question_type": "choice", "is_correct": False, "question": "..."},
            trace_collector=trace_collector,
        )
    )
    assert len(agent.stream_calls) == 2, "missing required sections must trigger repair"
    assert agent.stream_calls[0].get("max_tokens") == 1400
    assert agent.stream_calls[1].get("max_tokens") == 1400, "repair call must carry the same cap"
    sections = trace_collector["explanation_sections"]
    for key in ("verdict", "correct_answer", "why_wrong", "next_practice"):
        assert str(sections.get(key, "")).strip(), f"{key} must be non-empty post-fallback"
    miss = trace_collector["explanation_section_miss"]
    assert "why_wrong" in miss and "next_practice" in miss


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


@pytest.mark.parametrize("compact", [False, True])
def test_self_repair_prompt_is_slim_and_drops_history(
    monkeypatch: pytest.MonkeyPatch, compact: bool
) -> None:
    """Battle2 perf：self-repair 只发最小充分上下文——含题目/学员作答/缺段名单/检索依据，
    但**不含裁剪会话历史**；首轮 user_prompt 仍带历史（首轮行为不变）。两种 flag 都覆盖。"""
    history_sentinel = "HISTORY_SENTINEL_上一轮闲聊"
    grounding_sentinel = "GROUNDING_SENTINEL_教材第12章"
    question_sentinel = "QUESTION_SENTINEL_防火门顺序关闭"
    answer_sentinel = "ANSWER_SENTINEL_我选A"

    # 首轮只给 2 段（缺 why_wrong / next_practice）→ 触发 repair；第二轮补齐。
    repair_supplement = (
        "### 为什么错\n概念混淆。\n### 下一步\n抄 1 遍规范。\n"
        "### 逐项解析\nA 错；B 对；C 错；D 错。\n"
    )
    agent = _make_agent(monkeypatch, stream_outputs=[_PARTIAL_EXPLANATION, repair_supplement])
    _force_flag(monkeypatch, compact)
    trace_collector: dict[str, Any] = {}
    asyncio.run(
        agent.process(
            user_message=answer_sentinel,
            question_context={
                "question_id": "q_slim",
                "question_type": "choice",
                "is_correct": False,
                "question": question_sentinel,
            },
            history_context=history_sentinel,
            grounding_context=grounding_sentinel,
            trace_collector=trace_collector,
        )
    )

    assert len(agent.stream_calls) == 2, "缺段必须触发 self-repair"
    main_prompt = agent.stream_calls[0]["user_prompt"]
    repair_prompt = agent.stream_calls[1]["user_prompt"]

    # 首轮不变：历史仍在。
    assert history_sentinel in main_prompt, "首轮 user_prompt 必须仍带历史（首轮行为不变）"

    # repair = 充分集：题目、学员作答、缺段名单、检索依据齐全。
    assert question_sentinel in repair_prompt, "repair 必须含题干"
    assert answer_sentinel in repair_prompt, "repair 必须含学员作答"
    assert grounding_sentinel in repair_prompt, "repair 必须含检索依据（开放世界事实源，保留）"
    assert "why_wrong" in repair_prompt and "next_practice" in repair_prompt, "repair 必须含缺段名单"

    # slim：历史被丢弃。
    assert history_sentinel not in repair_prompt, "repair 不得携带裁剪会话历史"

    # repair 输出仍过必填段校验：4 必备段全非空、无缺段。
    sections = trace_collector["explanation_sections"]
    for key in ("verdict", "correct_answer", "why_wrong", "next_practice"):
        assert str(sections.get(key, "")).strip(), f"{key} 必须补齐非空"
    assert trace_collector["explanation_section_miss"] == [], "repair 后不应仍缺必备段"


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
    # 模板填充：所有 required keys（Battle2 S2-T1 后为 4 必备段 + 错题 option_analysis）都应有内容
    for key in ("verdict", "correct_answer", "why_wrong", "next_practice", "option_analysis"):
        assert sections.get(key), f"{key} should be filled by template fallback"
    # 条件段（knowledge_point/common_pitfall/mnemonic）缺失=合法省略，不模板兜底
    for key in ("knowledge_point", "common_pitfall", "mnemonic"):
        assert key not in sections
    # explanation_section_miss 应记录原始缺段名单（template 填充不修改 miss list）
    assert len(trace_collector["explanation_section_miss"]) > 0
