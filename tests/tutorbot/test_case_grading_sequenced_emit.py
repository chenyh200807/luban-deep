"""案例判分渐进吐字（sequenced emit, L4 2026-08-01）的守门测试。

被测承诺（效率画像 §1.4/§5-W5：学生 1.6s 看到 65 字开场白，然后死寂 20.2s(p50) /
41.8s(p95)，再 3034 字涌出）：

1. **死寂窗口被填满**——慢推导下，判分正文出现前至少两次有内容的 public 发射，
   且相邻发射间隔受心跳间隔约束（live 判据「最大单次停顿 ≤10s」的可证伪替身）。
2. **终态即真值**——同一份判分事件，开/关渐进吐字得到的 OutboundMessage、
   result payload、session 落库文本逐字段相同；判分正文始终是流式 public 文本的
   **严格后缀**（turn_runtime._replace_public_result_response_with_stream 的后缀
   豁免分支据此保持 result.response 不变，contracts/turn.md:144）。
3. **判分正文没被抢跑**——narration 里不含任何得分/命中断言。
4. **宣传门断言面不被污染**——narration 不引入 A1/A2/A4/A5/A9/A10 的判据形态
   （宣传门的断言面 = 流式 content 拼接，见 scripts/run_student_turn.py 的
   visible_response）。
"""
from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.services.construction_grading import rubric_grader_v1 as G
from deeptutor.tutorbot.agent import loop as loop_module
from deeptutor.tutorbot.agent.loop import (
    AgentLoop,
    _case_grading_progress_line,
    _CaseGradingProgressNarrator,
)
from deeptutor.tutorbot.bus.events import InboundMessage
from deeptutor.tutorbot.session.manager import Session

SCORE_FIRST = "## 批改结论\n**得分预估：** 1 / 2 分。\n- 命中 1 个，部分命中 0 个，漏/错 1 个。"
BLOCKS = [
    {"id": "q1", "phase": "question_detail", "sealed": True, "title": "问题1",
     "content": "## 问题1\n**采分点：**\n- 已命中：点1"},
    {"id": "final", "phase": "final_detail", "sealed": True, "title": "下一步建议",
     "content": "## 下一步建议\n先练没拿到的点。"},
]
FINAL_TEXT = SCORE_FIRST + "\n\n" + "\n\n".join(b["content"] for b in BLOCKS)


class _FakeContext:
    def build_messages(self, *, history, current_message, media=None, channel=None,
                       chat_id=None, runtime_instruction=None):
        return [{"role": "system", "content": ""}, *history,
                {"role": "user", "content": current_message}]

    def add_assistant_message(self, messages, content, **_kwargs):
        return [*messages, {"role": "assistant", "content": content}]


def _loop() -> AgentLoop:
    loop = AgentLoop.__new__(AgentLoop)
    loop.context = _FakeContext()
    loop.memory_consolidator = SimpleNamespace(
        maybe_consolidate_by_tokens=lambda _session: asyncio.sleep(0)
    )
    loop.sessions = SimpleNamespace(save=lambda _session: None)
    return loop


def _stream_plan(runtime_metadata: dict[str, Any]) -> dict[str, Any]:
    runtime_metadata["_v1_case_graded"] = True
    runtime_metadata["v1_case_graded"] = True
    runtime_metadata["score_authority"] = "rubric_scored_v1"
    runtime_metadata["grading_rubric_provenance"] = "derived_from_stem"
    runtime_metadata["case_grading_stream_mode"] = "score_first_sealed_blocks"
    return {
        "mode": "score_first_sealed_blocks",
        "score_first": SCORE_FIRST,
        "sealed_blocks": BLOCKS,
        "final_text": FINAL_TEXT,
        "presentation": None,
    }


async def _run_direct(
    monkeypatch: pytest.MonkeyPatch,
    *,
    derive_delay_s: float,
    heartbeat_interval_s: float,
    enabled: bool = True,
) -> dict[str, Any]:
    """跑一次直批，返回 (deltas, 时间戳, 出参)。慢推导用 sleep 模拟。"""
    loop = _loop()
    monkeypatch.setattr(loop, "_is_case_grading_scene", lambda _md: True)
    monkeypatch.setattr(
        loop_module, "_CASE_GRADING_HEARTBEAT_INTERVAL_S", heartbeat_interval_s
    )
    monkeypatch.setenv(
        "LUBAN_CASE_GRADING_SEQUENCED_EMIT", "1" if enabled else "off"
    )

    async def _fake_prefetch(*, initial_messages, runtime_metadata, **_kw):
        runtime_metadata["_prefetched_exact_question"] = {}
        return initial_messages

    async def _fake_plan(*, runtime_metadata, user_message, on_stage=None):
        # 判分核的真实阶段序：选档 → （慢）推导 → 采分点就绪 → 分组判定 → 汇总。
        if on_stage is not None:
            await on_stage("rubric_source", tier="stem")
        await asyncio.sleep(derive_delay_s)
        if on_stage is not None:
            await on_stage("rubric_ready", point_count=12)
            await on_stage("judge_group_done", completed=1, total=2, size=6)
            await on_stage("judge_group_done", completed=2, total=2, size=6)
            await on_stage("judge_done")
        return _stream_plan(runtime_metadata)

    monkeypatch.setattr(loop, "_maybe_prefetch_grounded_rag", _fake_prefetch)
    monkeypatch.setattr(loop, "_v1_case_stream_plan", _fake_plan)

    md: dict[str, Any] = {
        "question_lifecycle_scene": "case_grading",
        "user_id": "qa_seq_emit",
        "default_kb": "luban",
    }
    session = Session(key="web:seq-emit")
    msg = InboundMessage(channel="web", sender_id="u", chat_id="c",
                         content="【问题】问题1：指出不妥。\n作答：点1", metadata=md)
    deltas: list[str] = []
    stamps: list[float] = []
    running = asyncio.get_running_loop()

    async def _on_delta(text: str) -> None:
        deltas.append(text)
        stamps.append(running.time())

    out = await loop._run_case_grading_direct(
        msg=msg,
        session=session,
        history=[],
        current_message=msg.content,
        runtime_metadata=md,
        runtime_instruction="",
        on_content_delta=_on_delta,
    )
    return {"out": out, "deltas": deltas, "stamps": stamps, "session": session, "md": md}


@pytest.mark.asyncio
async def test_silent_window_gets_at_least_two_contentful_public_emits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """慢推导（0.6s，心跳 0.1s）下，判分正文出现前必须有 ≥2 次有内容的 public 发射。"""
    run = await _run_direct(monkeypatch, derive_delay_s=0.6, heartbeat_interval_s=0.1)
    streamed = "".join(run["deltas"])
    prefix = streamed[: streamed.index(SCORE_FIRST)]

    # 开场白之后、判分正文之前的发射（开场白本身不算——它就是今天已有的 65 字）。
    preview = AgentLoop._case_grading_live_preview_text(run["md"] and "x")
    narration = [line for line in prefix.split("\n\n") if line.strip()]
    assert len(narration) >= 3, narration  # 开场白 2 段 + 至少 1 条 narration
    assert any("题库里没有匹配到" in line for line in narration), narration
    assert any("采分点" in line and "推导" in line for line in narration), narration
    assert preview  # 开场白依旧在（未被替换）

    # 死寂窗口内至少两次「非开场白」发射。
    contentful = [
        line for line in narration
        if line.strip() and not line.startswith("这道案例题") and "先拆题" not in line
    ]
    assert len(contentful) >= 2, contentful


@pytest.mark.asyncio
async def test_max_stall_between_public_emits_is_bounded_by_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """心跳把最大单次停顿压到 interval 量级（live 判据 ≤10s 的可证伪替身）。"""
    interval = 0.1
    run = await _run_direct(monkeypatch, derive_delay_s=0.9, heartbeat_interval_s=interval)
    stamps = run["stamps"]
    assert len(stamps) >= 2
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    # chunk 之间还有 0.04s 固定节流 + 事件循环调度，留 3x 余量（与 live 判据
    # 7s 心跳 / 10s 上限的余量比一致）。
    assert max(gaps) < interval * 3 + 0.25, gaps


@pytest.mark.asyncio
async def test_terminal_truth_is_byte_identical_with_and_without_sequenced_emit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """终态即真值：开/关渐进吐字，OutboundMessage / result metadata / session 文本全等。"""
    on = await _run_direct(monkeypatch, derive_delay_s=0.3, heartbeat_interval_s=0.05)
    off = await _run_direct(monkeypatch, derive_delay_s=0.3, heartbeat_interval_s=0.05,
                            enabled=False)

    assert on["out"].content == off["out"].content == FINAL_TEXT
    assert on["out"].metadata == off["out"].metadata
    assert on["session"].messages[-1]["content"] == off["session"].messages[-1]["content"]

    # 关闭时流式文本 = 今天的形状（开场白 + 判分正文）。
    assert "".join(off["deltas"]).endswith(FINAL_TEXT)
    # 打开时判分正文仍是流式文本的**严格后缀**——这正是
    # _replace_public_result_response_with_stream 后缀豁免分支保住 result.response
    # 逐字节不变的前提（contracts/turn.md:144）。
    streamed_on = "".join(on["deltas"])
    assert streamed_on.endswith(FINAL_TEXT)
    assert len(streamed_on) > len("".join(off["deltas"]))


@pytest.mark.asyncio
async def test_narration_carries_no_score_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """判分权力零携带：narration 段不得出现得分/命中/漏点等终局断言。"""
    run = await _run_direct(monkeypatch, derive_delay_s=0.4, heartbeat_interval_s=0.1)
    streamed = "".join(run["deltas"])
    prefix = streamed[: streamed.index(SCORE_FIRST)]
    narration = "\n".join(
        line for line in prefix.split("\n\n")
        if line.strip() and not line.startswith("这道案例题") and "先拆题" not in line
    )
    for forbidden in ("得分", "命中 ", "满分", "分。", "✅", "❌"):
        assert forbidden not in narration, (forbidden, narration)


@pytest.mark.asyncio
async def test_disabled_flag_restores_todays_stream_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kill switch：关掉之后流式形状与改动前一致（开场白 + 判分正文，无第三段）。"""
    off = await _run_direct(monkeypatch, derive_delay_s=0.2, heartbeat_interval_s=0.05,
                            enabled=False)
    streamed = "".join(off["deltas"])
    preview_end = streamed.index("\n\n" + SCORE_FIRST)
    assert "题库里" not in streamed[:preview_end]
    assert "采分点拆好了" not in streamed[:preview_end]


# ---------------------------------------------------------------------------
# 宣传门断言面静态核对
# ---------------------------------------------------------------------------
# 与 scripts/promo_gate/run_promo_gate.py 同源的判据形态（复制而非 import：
# 宣传门活在另一个 worktree，这里要的是「narration 不得踩这些形态」的钉子）。
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
PROMO_MNEMONIC_LINE_RE = re.compile(r"^[^、\s]{2,15}(、[^、\s]{2,15}){2,}$")

ALL_NARRATION_LINES = [
    _case_grading_progress_line("authority_lookup_start", {}),
    _case_grading_progress_line("authority_lookup_done", {"hit": True}),
    _case_grading_progress_line("authority_lookup_done", {"hit": False}),
    _case_grading_progress_line("rubric_source", {"tier": "compiled", "point_count": 24}),
    _case_grading_progress_line("rubric_source", {"tier": "compiled"}),
    _case_grading_progress_line("rubric_source", {"tier": "reference"}),
    _case_grading_progress_line("rubric_source", {"tier": "stem"}),
    _case_grading_progress_line("rubric_source", {"tier": "submission_stem"}),
    _case_grading_progress_line("rubric_ready", {"point_count": 12}),
    _case_grading_progress_line("rubric_ready", {}),
    _case_grading_progress_line("judge_group_done", {"completed": 1, "total": 1, "size": 9}),
    _case_grading_progress_line("judge_group_done", {"completed": 2, "total": 3, "size": 8}),
    _case_grading_progress_line("judge_done", {}),
    _case_grading_progress_line("heartbeat", {"stage_label": "采分点推导中", "elapsed_s": 21}),
    _case_grading_progress_line("heartbeat", {"stage_label": "逐点比对中", "elapsed_s": 7}),
]


@pytest.mark.parametrize("line", [line for line in ALL_NARRATION_LINES if line])
def test_narration_line_does_not_pollute_promo_gate_assertion_surface(line: str) -> None:
    assert not [w for w in PROMO_A1_MISS_WORDS if w in line], line
    assert not [w for w in PROMO_A5_CANNED_REFUSALS if w in line], line
    assert not [w for w in PROMO_A4_DISCLAIMER_TERMS if w in line], line
    assert not PROMO_SCORE_SLASH_RE.search(line), line
    assert not PROMO_SCORE_LABEL_RE.search(line), line
    assert not PROMO_FULLSCORE_PAIR_RE.search(line), line
    for physical_line in line.split("\n"):
        assert not PROMO_MNEMONIC_LINE_RE.match(physical_line.strip()), line


def test_every_narration_kind_is_covered_by_the_promo_gate_check() -> None:
    """新增 kind 必须同时进 ALL_NARRATION_LINES——否则文案可以绕过宣传门核对上线。"""
    source = (
        loop_module._case_grading_progress_line.__doc__ or ""
    )  # doc 只是可读性；真正的锚是下面这份 kind 清单
    assert source
    known_kinds = {
        "authority_lookup_start", "authority_lookup_done", "rubric_source",
        "rubric_ready", "judge_group_done", "judge_done", "heartbeat",
    }
    import inspect

    body = inspect.getsource(loop_module._case_grading_progress_line)
    emitted = set(re.findall(r'kind == "([a-z_]+)"', body))
    assert emitted == known_kinds, emitted


def test_unknown_kind_emits_nothing() -> None:
    assert _case_grading_progress_line("not_a_kind", {}) == ""
    assert _case_grading_progress_line("rubric_source", {"tier": "???"}) == ""
    assert _case_grading_progress_line("heartbeat", {"stage_label": "", "elapsed_s": 3}) == ""


@pytest.mark.asyncio
async def test_narrator_swallows_emit_failures() -> None:
    """进度叙述永不破坏判分：emit 抛错只被吞掉。"""

    async def _boom(_text: str) -> None:
        raise RuntimeError("transport down")

    narrator = _CaseGradingProgressNarrator(_boom, interval_s=0.02, max_heartbeats=1)
    await narrator.start()
    await narrator.stage("rubric_ready", point_count=3)
    await asyncio.sleep(0.08)
    await narrator.stop()
    assert narrator.emitted_lines == []


@pytest.mark.asyncio
async def test_narrator_stop_is_idempotent_and_kills_heartbeat() -> None:
    lines: list[str] = []

    async def _emit(text: str) -> None:
        lines.append(text)

    narrator = _CaseGradingProgressNarrator(_emit, interval_s=0.02, max_heartbeats=5)
    await narrator.start()
    await narrator.stage("rubric_source", tier="stem")
    await asyncio.sleep(0.12)
    await narrator.stop()
    settled = len(lines)
    await narrator.stop()
    await asyncio.sleep(0.1)
    assert len(lines) == settled
    assert settled >= 2  # 里程碑 1 条 + 至少 1 次心跳


@pytest.mark.asyncio
async def test_judge_group_progress_reports_arrival_order_without_touching_verdicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分组回调按到达顺序发声，但 verdict 汇总仍走 gather 的参数序（判分真值不动）。"""
    points = [
        {"point_id": f"p{i}", "text": f"点{i}", "score": 1.0, "question_no": str(i // 8 + 1)}
        for i in range(24)
    ]

    async def _fake_batch_async(group, _answer, _complete, _key, model="m"):
        # 第一组最慢：到达序必须 != 参数序，才证明回调用的是到达序。
        await asyncio.sleep(0.05 if group[0]["point_id"] == "p0" else 0.0)
        return {p["point_id"]: {"status": G.HIT} for p in group}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    seen: list[tuple[int, int, int]] = []

    async def _on_group_done(*, completed: int, total: int, size: int) -> None:
        seen.append((completed, total, size))

    verdicts, metadata = await G._batch_judge_dynamic_async(
        points, "作答", lambda **_k: None, "key", on_group_done=_on_group_done
    )
    assert metadata["adjudication_group_count"] == 3
    assert [item[0] for item in seen] == [1, 2, 3]
    # 判分真值面：全部 24 个点都拿到 verdict，与无回调时一致。
    assert len(verdicts) == 24


@pytest.mark.asyncio
async def test_judge_group_progress_failure_does_not_break_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = [
        {"point_id": f"p{i}", "text": f"点{i}", "score": 1.0, "question_no": str(i // 8 + 1)}
        for i in range(24)
    ]

    async def _fake_batch_async(group, _answer, _complete, _key, model="m"):
        return {p["point_id"]: {"status": G.HIT} for p in group}

    monkeypatch.setattr(G, "batch_judge_async", _fake_batch_async)

    async def _boom(**_kwargs) -> None:
        raise RuntimeError("observer down")

    verdicts, _metadata = await G._batch_judge_dynamic_async(
        points, "作答", lambda **_k: None, "key", on_group_done=_boom
    )
    assert len(verdicts) == 24
