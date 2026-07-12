"""Battle2 S1 同病同修:公开记忆(SUMMARY+PROFILE)每轮双 LLM 重写的计数门控。

镜像 learner_state 已上线的 summary-maintainer 门控:每 N 个实质轮次才跑一次
(profile+summary 两跳共用一个门决策);门 skip 时零 LLM 调用;阈值达到时恢复;
任何门异常一律 fail-open(宁可多跑不可漏跑)。
"""

from __future__ import annotations

import asyncio

from deeptutor.services.memory.service import (
    _MEMORY_GATE_TURN_THRESHOLD,
    _MemoryGateState,
    MemoryService,
)
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


def _make_service(tmp_path):
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    return MemoryService(
        path_service=type(
            "PathServiceStub",
            (),
            {"get_memory_dir": lambda self: tmp_path / "memory"},
        )(),
        store=store,
    )


class _CountingStream:
    """每次被 await-iterate 就 +1,产出一份合法的 profile 重写。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **_kwargs):
        self.calls += 1

        async def _gen():
            yield "## Preferences\n- Prefer concise answers."

        return _gen()


def _refresh(service, **kwargs):
    base = dict(
        user_message="Please remember I like concise answers about waterproofing.",
        assistant_message="Got it, I'll keep answers concise.",
        session_id="s1",
        capability="chat",
        language="en",
    )
    base.update(kwargs)
    return asyncio.run(service.refresh_from_turn(**base))


def test_cold_start_runs_then_gate_throttles_middle_turns(monkeypatch, tmp_path) -> None:
    """冷启动(从未运行)立即跑;之后门把中间轮次节流,每 N 轮才恢复一次真重写。"""
    service = _make_service(tmp_path)
    stream = _CountingStream()
    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", stream)

    # Turn 1: 冷启动 -> 立即跑 -> profile+summary 两跳 = 2 次 LLM 调用。
    _refresh(service)
    assert stream.calls == 2
    assert service._gate_state.turns_since_run == 0
    assert service._gate_state.last_run_at  # 已标记运行过

    # 之后连续 N-1 轮:门 skip,零 LLM 调用。
    for _ in range(_MEMORY_GATE_TURN_THRESHOLD - 1):
        result = _refresh(service)
        assert result.changed is False
    assert stream.calls == 2  # 仍然是冷启动那两跳,skip 期间零调用

    # 第 N 轮:计数达到阈值 -> 恢复重写 -> 再加两跳。
    _refresh(service)
    assert stream.calls == 4
    assert service._gate_state.turns_since_run == 0


def test_gate_skip_returns_current_snapshot_without_rewrite(monkeypatch, tmp_path) -> None:
    """门 skip 分支不改文件、不调用 LLM,返回当前快照。"""
    service = _make_service(tmp_path)
    # 先让冷启动那轮跑掉(用 no-change 流,避免落文件干扰断言)。
    async def _no_change(**_kwargs):
        yield "NO_CHANGE"

    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _no_change)
    _refresh(service)  # 冷启动运行,turns_since_run 归 0

    # 现在换成"若被调用就爆炸"的流,证明 skip 轮零 LLM 调用。
    def _explode(**_kwargs):
        raise AssertionError("LLM must not be called on a throttled/skip turn")

    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _explode)
    result = _refresh(service)
    assert result.changed is False
    assert service._gate_state.turns_since_run == 1
    assert not service._path("profile").exists()
    assert not service._path("summary").exists()


def test_gate_decision_fails_open_on_exception(tmp_path) -> None:
    """门内部异常一律判定为立即运行(run_fail_open),绝不 fail-closed。"""
    service = _make_service(tmp_path)
    # 用一个访问 .last_run_at 会抛异常的对象替换门状态。
    service._gate_state = object()  # type: ignore[assignment]
    assert service._memory_gate_decision(capability="chat") == "run_fail_open"


def test_capability_passthrough_never_throttled(tmp_path) -> None:
    """guide*/notebook* capability 走直通,即使计数未达阈值也运行(镜像 S1 never-skip 集)。"""
    service = _make_service(tmp_path)
    # 已运行过一次且计数尚未达阈值 -> 普通 capability 会 skip。
    service._gate_state = _MemoryGateState(turns_since_run=0, last_run_at="2026-07-12T00:00:00")
    assert service._memory_gate_decision(capability="chat") == "skip_throttled"
    assert service._memory_gate_decision(capability="guide") == "run_capability"
    assert service._memory_gate_decision(capability="notebook_card") == "run_capability"


def test_llm_exception_does_not_reset_counter(monkeypatch, tmp_path) -> None:
    """一次运行中途 LLM 抛异常时不重置计数器,让陈旧计数下一轮继续触发运行(fail-open)。"""
    service = _make_service(tmp_path)
    # 造一个已达阈值、必然 run 的状态。
    service._gate_state = _MemoryGateState(
        turns_since_run=_MEMORY_GATE_TURN_THRESHOLD, last_run_at="2026-07-12T00:00:00"
    )

    def _explode(**_kwargs):
        raise RuntimeError("upstream LLM down")

    monkeypatch.setattr("deeptutor.services.memory.service.llm_stream", _explode)
    try:
        _refresh(service)
    except RuntimeError:
        pass
    # 异常发生在重置行之前,计数器保持陈旧(未被重置为新 _MemoryGateState)。
    assert service._gate_state.turns_since_run == _MEMORY_GATE_TURN_THRESHOLD
