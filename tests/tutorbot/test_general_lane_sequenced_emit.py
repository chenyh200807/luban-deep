"""通用 agent-loop 首答窗口渐进吐字（L4 通用道，2026-08-01 task#29）的守门测试。

被测承诺（`docs/原始数据/数据盘点/2026-08-01-历史错误逐案重放回归.md` §7.4 实证：
同一 payload 四次重放 TTFT 64.3s / 56.5s / 40.0s / 断线，走判分链的同题只要 2.6s，
差别就是**只有判分链装了渐进吐字**）：

1. **死寂窗口被填满**——慢 LLM 下，终局正文出现前至少两次**有内容**的 public 发射，
   相邻发射间隔受心跳间隔约束（live 判据「首答窗口 ≤10s 内有内容发射」的可证伪替身）。
2. **终态即真值**——同一条链，开/关渐进吐字得到的 `final_content` / `tools_used` /
   messages 尾部逐字段相同；终局正文始终是流式 public 文本的**严格后缀**
   （turn_runtime._replace_public_result_response_with_stream 的同源后缀豁免据此
   保持 result.response 逐字节不变，contracts/turn.md「渐进发射不改变终态」(a)）。
3. **逐轮解除武装**——通用道不知道哪一轮是终局轮，靠「本轮出现真实正文 delta 就停口」
   兑现严格后缀：工具轮里模型先吐了独白，叙述也绝不会插到终局正文中间。
4. **观察者零权力**——叙述发射抛异常不改变终态。
5. **宣传门断言面不被污染**——叙述不引入 A1/A2/A4/A5/A9/A10 的判据形态。
6. **kill switch**——关掉后流形状逐字节回到未改动前。
"""
from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from deeptutor.tutorbot.agent import loop as loop_module
from deeptutor.tutorbot.agent.loop import (
    _general_lane_progress_line,
    _GeneralLaneProgressNarrator,
)

ANSWER = (
    "室内环境污染物浓度检测的点数按房间使用面积确定：小于 50m² 时不少于 1 个点，"
    "50~100m² 时不少于 2 个点，100~500m² 时不少于 3 个点。标准间使用面积 200m²，"
    "因此至少布置 3 个检测点。甲醛的限值按《民用建筑工程室内环境污染控制标准》"
    "GB50325-2020 表 6.0.4 取 0.07mg/m³，实测 0.11mg/m³ 已超出限值，应判定为不符合要求，"
    "需查明污染源、整改后重新检测。"
)
MONOLOGUE = "我先看一下检索到的规范原文。"


# --- 宣传门断言面（与 tests/tutorbot/test_case_grading_sequenced_emit.py 同源） ---
PROMO_A1_MISS_WORDS = [
    "未作答", "漏答", "未见作答", "未提交", "未回答", "没有作答", "未给出作答", "缺答", "未答",
    "漏点", "漏掉", "漏/错", "没有覆盖", "未覆盖", "需要补",
]
PROMO_A5_CANNED_REFUSALS = ["拆小", "一道一道发", "一题一题发", "分批发送", "把题目分开发"]
PROMO_A4_DISCLAIMER_TERMS = [
    "诊断得分预估", "得分预估", "预估得分", "诊断分", "非官方", "不硬估",
    "不代表官方", "无官方评分标准", "仅供参考", "参考性评分", "无法给出官方",
]
PROMO_SCORE_SLASH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*分")
PROMO_SCORE_LABEL_RE = re.compile(r"得分[:：]?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
PROMO_FULLSCORE_PAIR_RE = re.compile(r"得\s*(\d+(?:\.\d+)?)\s*分[^。\n]{0,20}?满分\s*(\d+(?:\.\d+)?)")



def _narration_lines(chunks: list[str]) -> list[str]:
    """把 sink 收到的**分片**还原成叙述**条数**。

    `_emit_visible_text_deltas` 会把一条叙述切成多片发出，直接数 sink 调用次数会把
    「一条被切成三片」误判成「发了三条」—— 判据必须落在条数上。
    """
    return [seg.strip() for seg in "".join(chunks).split("\n\n") if seg.strip()]


class _SlowProvider(LLMProvider):
    """一轮 rag 取证 + 一轮终答，每轮都慢 —— 复刻 live 的 40-65s 空屏形态。

    ``monologue_in_tool_round`` 打开时，工具轮先流一段模型独白，用来验证「叙述永不跟在
    同一轮的正文 delta 之后」以及严格后缀不变量在有独白时依然成立。
    """

    def __init__(self, delay_s: float, *, monologue_in_tool_round: bool = False) -> None:
        super().__init__()
        self._delay_s = delay_s
        self._monologue = monologue_in_tool_round
        self.calls = 0

    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None,
                   on_content_delta=None) -> LLMResponse:
        self.calls += 1
        await asyncio.sleep(self._delay_s)
        if self.calls == 1:
            if self._monologue and on_content_delta is not None:
                await on_content_delta(MONOLOGUE)
            return LLMResponse(
                content=MONOLOGUE if self._monologue else "",
                tool_calls=[ToolCallRequest(id="c1", name="rag", arguments={"topic": "甲醛限值"})],
            )
        if on_content_delta is not None:
            # 终局正文分两段流，中间再慢一次：心跳若没被解除武装就会插进正文中间。
            await on_content_delta(ANSWER[:40])
            await asyncio.sleep(self._delay_s)
            await on_content_delta(ANSWER[40:])
        return LLMResponse(content=ANSWER, finish_reason="stop")

    def get_default_model(self) -> str:
        return "fake-model"


def _build_loop(provider: LLMProvider, tmp_path):
    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.agent.tools.base import Tool
    from deeptutor.tutorbot.agent.tools.registry import ToolRegistry
    from deeptutor.tutorbot.bus.queue import MessageBus

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

    class _RagTool(Tool):
        @property
        def name(self) -> str:
            return "rag"

        @property
        def description(self) -> str:
            return "dummy retrieval"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {"topic": {"type": "string"}},
                    "required": ["topic"]}

        async def execute(self, **kwargs: Any) -> str:
            return "GB50325-2020 表 6.0.4：甲醛限值 0.07mg/m³。"

    loop.tools = ToolRegistry()
    loop.tools.register(_RagTool())
    return loop


async def _drive(loop, *, capture: list[str], stamps: list[float] | None = None):
    async def _on_delta(text: str) -> None:
        capture.append(text)
        if stamps is not None:
            stamps.append(asyncio.get_running_loop().time())

    return await loop._run_agent_loop(
        [{"role": "user", "content": "标准间 200m² 甲醛 0.11 合格吗，检测几个点？"}],
        runtime_metadata={"default_tools": ["rag"], "mode_execution_policy": {"max_tool_rounds": 2}},
        on_content_delta=_on_delta,
    )


@pytest.fixture(autouse=True)
def _logger_pollution_shield(monkeypatch: pytest.MonkeyPatch) -> None:
    """全量跑时 `tests/tutorbot/test_memory_consolidator.py` 在 **import 期**把 fake loguru
    塞进 `sys.modules`，`loop_module.logger` 会退化成缺 `info` 的 SimpleNamespace（既有
    隔离污染，本 PR 不动别人的文件）。这里只在本模块内补齐缺失方法，由 monkeypatch 还原，
    不留任何全局副作用。"""
    logger = loop_module.logger
    for name in ("trace", "debug", "info", "success", "warning", "error", "exception"):
        if not hasattr(logger, name):
            monkeypatch.setattr(logger, name, lambda *a, **k: None, raising=False)


@pytest.fixture()
def fast_heartbeat(monkeypatch: pytest.MonkeyPatch) -> float:
    """把心跳间隔缩到测试量级——被测的是**机制**，生产量级由下面的常量断言单独钉。"""
    monkeypatch.setattr(loop_module, "_GENERAL_LANE_HEARTBEAT_INTERVAL_S", 0.05)
    monkeypatch.setattr(loop_module, "_GENERAL_LANE_MAX_HEARTBEATS", 12)
    return 0.05


def test_live_heartbeat_budget_matches_the_ten_second_criterion() -> None:
    """live 判据「首答窗口内最大单次停顿 ≤10s」的常量替身：7s 留 3s 余量。"""
    assert loop_module._GENERAL_LANE_HEARTBEAT_INTERVAL_S <= 10.0
    assert loop_module._GENERAL_LANE_MAX_HEARTBEATS >= 4


@pytest.mark.asyncio
async def test_silent_window_is_filled_before_the_final_body(tmp_path, fast_heartbeat) -> None:
    """慢 LLM 下，终局正文出现前至少两次有内容发射，且相邻发射间隔受心跳约束。"""
    provider = _SlowProvider(delay_s=0.45)
    loop = _build_loop(provider, tmp_path)
    capture: list[str] = []
    stamps: list[float] = []

    final_content, _tools, _msgs = await _drive(loop, capture=capture, stamps=stamps)

    streamed = "".join(capture)
    assert final_content == ANSWER
    prefix = streamed[: len(streamed) - len(ANSWER)]
    narration_lines = [line for line in prefix.split("\n\n") if line.strip()]  # noqa: E501
    assert len(narration_lines) >= 2, narration_lines

    # 首答窗口内的最大单次停顿：拿 prefix 期间的发射时刻验，上界给心跳间隔 4 倍余量
    # （测试机调度抖动 + 每轮 0.45s 的 provider 慢）。
    prefix_stamps = stamps[: len(narration_lines)]
    gaps = [b - a for a, b in zip(prefix_stamps, prefix_stamps[1:])]
    assert gaps, prefix_stamps
    assert max(gaps) <= fast_heartbeat * 4 + 0.5, gaps


@pytest.mark.asyncio
@pytest.mark.parametrize("monologue", [False, True])
async def test_final_body_is_a_strict_suffix_of_the_stream(tmp_path, fast_heartbeat, monologue) -> None:
    """严格后缀不变量：叙述全部落在终局正文之前，正文中途也不被心跳插字。"""
    provider = _SlowProvider(delay_s=0.3, monologue_in_tool_round=monologue)
    loop = _build_loop(provider, tmp_path)
    capture: list[str] = []

    final_content, _tools, _msgs = await _drive(loop, capture=capture)

    streamed = "".join(capture)
    assert final_content == ANSWER
    assert streamed.endswith(ANSWER), streamed[-120:]
    assert streamed != ANSWER  # 确实发生了渐进发射，否则这条测试是空转
    if monologue:
        # 工具轮的模型独白在正文之前，不影响后缀性；且它之后仍有叙述（下一轮重新武装）。
        assert streamed.index(MONOLOGUE) < streamed.rindex(ANSWER)


@pytest.mark.asyncio
async def test_terminal_state_is_field_by_field_identical_with_and_without_narration(
    tmp_path, fast_heartbeat, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开/关渐进吐字的终态逐字段等价；关掉后流形状逐字节回到未改动前。"""
    monkeypatch.delenv("LUBAN_GENERAL_LANE_SEQUENCED_EMIT", raising=False)
    on_capture: list[str] = []
    on_final, on_tools, on_msgs = await _drive(
        _build_loop(_SlowProvider(delay_s=0.05), tmp_path), capture=on_capture
    )

    monkeypatch.setenv("LUBAN_GENERAL_LANE_SEQUENCED_EMIT", "off")
    off_capture: list[str] = []
    off_final, off_tools, off_msgs = await _drive(
        _build_loop(_SlowProvider(delay_s=0.05), tmp_path), capture=off_capture
    )

    assert on_final == off_final == ANSWER
    assert on_tools == off_tools == ["rag"]
    assert on_msgs[-1] == off_msgs[-1]
    assert [m.get("role") for m in on_msgs] == [m.get("role") for m in off_msgs]
    # kill switch 关掉 = 流里一个字的叙述都没有
    assert "".join(off_capture) == ANSWER
    assert "".join(on_capture) != ANSWER


@pytest.mark.asyncio
async def test_narration_failure_never_changes_the_terminal_answer(
    tmp_path, fast_heartbeat, monkeypatch: pytest.MonkeyPatch
) -> None:
    """观察者零权力：叙述发射整体抛异常，终态不受任何影响。"""
    def _boom(kind: str, facts: dict[str, Any]) -> str:
        raise RuntimeError("narration exploded")

    monkeypatch.setattr(_GeneralLaneProgressNarrator, "_line", staticmethod(_boom))
    capture: list[str] = []
    final_content, tools_used, _msgs = await _drive(
        _build_loop(_SlowProvider(delay_s=0.05), tmp_path), capture=capture
    )
    assert final_content == ANSWER
    assert tools_used == ["rag"]
    assert "".join(capture) == ANSWER


@pytest.mark.parametrize(
    "kind,facts",
    [
        ("loop_start", {}),
        ("round_start", {"iteration": 2}),
        ("tool_call", {"tool": "rag", "index": 2}),
        ("tool_call", {"tool": "web_search", "index": 1}),
        ("tool_call", {"tool": "exec", "index": 1}),
        ("tool_call", {"tool": "mystery_tool", "index": 1}),
        ("tool_result", {"index": 1}),
        ("tool_result", {"index": 3}),
        ("synthesizing", {}),
        ("heartbeat", {"stage_label": "还在检索原文", "elapsed_s": 14}),
    ],
)
def test_narration_never_pollutes_the_promo_gate_assertion_surface(kind, facts) -> None:
    line = _general_lane_progress_line(kind, facts)
    assert line, (kind, facts)
    assert not [w for w in PROMO_A1_MISS_WORDS if w in line], line
    assert not [w for w in PROMO_A5_CANNED_REFUSALS if w in line], line
    assert not [w for w in PROMO_A4_DISCLAIMER_TERMS if w in line], line
    assert not PROMO_SCORE_SLASH_RE.search(line), line
    assert not PROMO_SCORE_LABEL_RE.search(line), line
    assert not PROMO_FULLSCORE_PAIR_RE.search(line), line


@pytest.mark.parametrize(
    "kind,facts",
    [
        ("round_start", {"iteration": 1}),
        ("tool_call", {"tool": "", "index": 1}),
        ("heartbeat", {"stage_label": "", "elapsed_s": 3}),
        ("heartbeat", {"stage_label": "还在检索原文", "elapsed_s": 0}),
        ("unknown_kind", {}),
    ],
)
def test_narration_stays_silent_without_a_supporting_fact(kind, facts) -> None:
    """没有事实支撑的 kind 一律不发（文案权威是纯函数，不许编）。"""
    assert _general_lane_progress_line(kind, facts) == ""


@pytest.mark.asyncio
async def test_disarm_and_rearm_is_round_scoped() -> None:
    """逐轮解除武装的单元级判据：正文 delta 之后停口，下一轮 begin_round 才恢复。"""
    emitted: list[str] = []

    async def _emit(text: str) -> None:
        emitted.append(text)

    narrator = _GeneralLaneProgressNarrator(_emit, interval_s=0, max_heartbeats=0)
    narrator.begin_round()
    await narrator.stage("loop_start")
    assert len(emitted) == 1
    await narrator.note_content_delta()
    await narrator.stage("tool_call", tool="rag", index=1)
    assert len(emitted) == 1, emitted  # 本轮已停口
    narrator.begin_round()
    await narrator.stage("tool_call", tool="rag", index=2)
    assert len(emitted) == 2, emitted
    await narrator.stop()


# ==========================================================================================
# 2026-08-01 live 验收不过（首答窗口 17.3s 空屏）的逐条回归
#
# 实测：1.6s 只有一个 progress 芯片，轮首播报直到 17.3s 才出现，且与工具边界叙述几乎同刻
# —— 典型的「全部憋着、被后来的字一起冲开」形态。四个缺陷叠加，逐条钉死。
# ==========================================================================================


def test_first_narration_line_cannot_open_the_answer_shape_gate() -> None:
    """病根前提：起流闸的判据是「像不像正经答案」，单行短叙述**永远**过不了。

    这条不是在断言期望行为，而是钉住 `_should_start_public_delta_stream` 的性质 ——
    正因为它恒 False，sanctioned narration 才必须走独立 sink 绕闸（见下一条）。
    闸本身不许为了叙述放松（放松 = 把模型独白也放进流，正是案②刚治的病）。
    """
    from deeptutor.capabilities.tutorbot import TutorBotCapability

    for kind in ("retrieval_prefetch", "loop_start", "synthesizing"):
        line = "\n\n" + _general_lane_progress_line(kind, {})
        assert TutorBotCapability._should_start_public_delta_stream(line) is False, kind
        # 但它也不该被当成模型独白 block 掉 —— 只是「还不够像答案」。
        assert TutorBotCapability._should_block_public_delta_stream(line) is False, kind


@pytest.mark.asyncio
async def test_sanctioned_narration_sink_streams_the_very_first_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """live 判据的单元替身：**第一条**叙述必须当场出流，不许等第二条来冲开。

    对照组用同一段文字走 `on_content_delta`（模型正文入口）—— 它应当被起流闸扣住，
    从而证明「差别来自 sink 的声明，不是来自文案凑巧变长了」。
    """
    from deeptutor.capabilities.tutorbot import TutorBotCapability
    from deeptutor.core.context import UnifiedContext
    from deeptutor.core.stream import StreamEvent, StreamEventType
    from deeptutor.core.stream_bus import StreamBus

    first_line = "\n\n" + _general_lane_progress_line("retrieval_prefetch", {})

    def _fake_manager(use_narration_sink: bool):
        class FakeManager:
            async def ensure_bot_running(self, bot_id: str, config=None):
                return SimpleNamespace(running=True)

            def build_chat_session_key(self, bot_id, conversation_id, user_id=None) -> str:
                return f"bot:{bot_id}:chat:{conversation_id}"

            def _infer_conversation_title(self, text: str) -> str:
                return text[:8]

            async def send_message(self, *, on_content_delta=None,
                                   on_progress_narration=None, **_kw: Any) -> str:
                sink = on_progress_narration if use_narration_sink else on_content_delta
                if sink is not None:
                    await sink(first_line)
                return ANSWER

        return FakeManager()

    async def _run(use_narration_sink: bool) -> list[StreamEvent]:
        monkeypatch.setattr(
            "deeptutor.capabilities.tutorbot.get_tutorbot_manager",
            lambda: _fake_manager(use_narration_sink),
        )
        context = UnifiedContext(
            session_id="session-first-emit",
            user_message="标准间 200m² 甲醛 0.11 合格吗，检测几个点？",
            enabled_tools=["rag"],
            knowledge_bases=["construction-exam"],
            config_overrides={"bot_id": "construction-exam-coach", "chat_mode": "smart"},
            metadata={"billing_context": {"user_id": "u1", "source": "wx_miniprogram"}},
            language="zh",
        )
        bus = StreamBus()
        events: list[StreamEvent] = []

        async def _consume() -> None:
            async for event in bus.subscribe():
                events.append(event)

        consumer = asyncio.create_task(_consume())
        await asyncio.sleep(0)
        await TutorBotCapability().run(context, bus)
        await asyncio.sleep(0)
        await bus.close()
        await consumer
        return events

    monkeypatch.setenv("TUTORBOT_STREAM_PUBLIC_DELTAS", "1")

    narration_events = [
        e for e in await _run(True)
        if e.type == StreamEventType.CONTENT and "正在去教材和规范原文里找" in (e.content or "")
    ]
    assert narration_events, "sanctioned narration sink 必须让第一条叙述当场出流"
    assert narration_events[0].metadata.get("call_kind") == "progress_narration"

    control_events = [
        e for e in await _run(False)
        if e.type == StreamEventType.CONTENT and "正在去教材和规范原文里找" in (e.content or "")
    ]
    assert not control_events, "对照组：同一段字走模型正文入口时应被起流闸扣住（病根本身）"


@pytest.mark.asyncio
async def test_think_only_deltas_do_not_disarm_the_round(tmp_path, fast_heartbeat) -> None:
    """推理模型的 `<think>` delta 不产生任何 public 文本，不许把整轮叙述关掉。

    旧实现在 `stream_stripper.feed()` **之前**解除武装 —— 模型想多久，学生空屏多久。
    """
    class _ThinkingProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                       temperature=0.7, reasoning_effort=None, tool_choice=None,
                       on_content_delta=None) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                if on_content_delta is not None:
                    await on_content_delta("<think>")
                    for _ in range(6):
                        await on_content_delta("反复推敲这道题的依据……")
                        await asyncio.sleep(0.06)
                    await on_content_delta("</think>")
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCallRequest(id="c1", name="rag", arguments={"topic": "甲醛"})],
                )
            if on_content_delta is not None:
                await on_content_delta(ANSWER)
            return LLMResponse(content=ANSWER, finish_reason="stop")

        def get_default_model(self) -> str:
            return "fake-model"

    capture: list[str] = []
    at_tool_boundary: dict[str, int] = {}

    async def _on_delta(text: str) -> None:
        capture.append(text)

    async def _on_tool_call(name: str, args: dict[str, Any]) -> None:
        at_tool_boundary.setdefault("at", len(capture))

    loop = _build_loop(_ThinkingProvider(), tmp_path)
    final_content, _tools, _msgs = await loop._run_agent_loop(
        [{"role": "user", "content": "标准间 200m² 甲醛 0.11 合格吗？"}],
        runtime_metadata={"default_tools": ["rag"],
                          "mode_execution_policy": {"max_tool_rounds": 2}},
        on_content_delta=_on_delta,
        on_tool_call=_on_tool_call,
    )
    streamed = "".join(capture)
    assert final_content == ANSWER
    assert streamed.endswith(ANSWER)
    # 判据必须落在 **think 窗口之内**（工具边界之前）：旧实现在 think 期间彻底噤声，
    # 只有 round 2 的 begin_round 才补一条 —— 那已经是学生等完之后了。
    before_tool = _narration_lines(capture[: at_tool_boundary.get("at", 0)])
    assert len(before_tool) >= 2, (
        f"think 窗口内只落了 {len(before_tool)} 条叙述 —— 推理期又被噤声: {before_tool}"
    )
    # 而 think 正文本身一个字都不许进 public 流
    assert "推敲" not in streamed and "<think>" not in streamed


@pytest.mark.asyncio
async def test_disarmed_heartbeat_does_not_burn_its_whole_budget(monkeypatch) -> None:
    """解除武装期间心跳必须**睡着等**，不许在无 await 的紧循环里把预算烧光。

    旧实现：`_emit_line` 被 `_may_emit()` 挡下时不刷新 `_last_emit_at`，于是 wait_s 恒 ≤0，
    12 次预算在一个 tick 内烧完、任务退出，之后整轮再无心跳。
    """
    emitted: list[str] = []

    async def _emit(text: str) -> None:
        emitted.append(text)

    narrator = _GeneralLaneProgressNarrator(_emit, interval_s=0.05, max_heartbeats=6)
    narrator.begin_round()
    await narrator.stage("loop_start")          # 设 stage_label，让心跳有话可说
    await narrator.note_content_delta()          # 解除武装
    await narrator.start()
    await asyncio.sleep(0.3)                     # 远超 6 × 0.05 的紧循环耗时
    await narrator.stop()

    assert narrator._heartbeats == 0, "解除武装期间不许消耗心跳预算"
    assert len(emitted) == 1, emitted


@pytest.mark.asyncio
async def test_narration_lands_before_the_first_tool_boundary(tmp_path, fast_heartbeat) -> None:
    """live 失败的形态判据：叙述不许攒到工具边界才一起 flush。

    round 1 的 provider 很慢，工具调用发生在最后；断言首答窗口里的叙述在**工具边界之前**
    就已经落到 sink 上（旧实现里 loop_start 与 tool_call 几乎同刻）。
    """
    capture: list[str] = []
    tool_boundary_index: dict[str, int] = {}

    async def _on_delta(text: str) -> None:
        capture.append(text)

    async def _on_tool_call(name: str, args: dict[str, Any]) -> None:
        tool_boundary_index["at"] = len(capture)

    loop = _build_loop(_SlowProvider(delay_s=0.5), tmp_path)
    await loop._run_agent_loop(
        [{"role": "user", "content": "标准间 200m² 甲醛 0.11 合格吗？"}],
        runtime_metadata={"default_tools": ["rag"], "mode_execution_policy": {"max_tool_rounds": 2}},
        on_content_delta=_on_delta,
        on_tool_call=_on_tool_call,
    )

    assert "at" in tool_boundary_index, "本用例必须真的走到工具边界"
    before_tool = _narration_lines(capture[: tool_boundary_index["at"]])
    assert len(before_tool) >= 2, (
        f"工具边界之前只落了 {len(before_tool)} 条叙述 —— "
        f"首答窗口又被攒到边界才 flush: {before_tool}"
    )
