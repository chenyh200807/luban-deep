from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

from deeptutor.tutorbot.agent.memory import MemoryConsolidator


# ---------------------------------------------------------------------------
# 隔离污染防复发闸（task#30，2026-08-01）
#
# 病灶：本文件（及另外五处）曾在 **import 期**把 fake `loguru` / `json_repair` /
# `tiktoken` 塞进 `sys.modules`。pytest 在跑第一个用例前就把整个目录的测试模块**全部
# import 完**，所以谁先落地谁赢——`tests/tutorbot/providers/` 按路径序排在 `test_*.py`
# 之前，它那份 `logger = SimpleNamespace(warning=...)`（**只有 warning**）成了全目录的
# `loguru`，此后任何走到 `logger.info(...)` 的模块级 logger 一律 AttributeError。
# 实测代价：`pytest tests/tutorbot/` 恒 43 failed / 单跑各文件全绿，多兵只能靠「失败集
# 与基线 diff」自证清白。
#
# 根因不是「fake 不够全」而是「fake 根本不该存在」：loguru / json-repair / tiktoken
# 都是 requirements/{server,tutorbot}.txt 里的**硬依赖**，任何能 import deeptutor 的
# 环境必然装了真货。六处 shim 全删，本闸防它们回流。
# ---------------------------------------------------------------------------

_STUBBED_HARD_DEPS = ("loguru", "json_repair", "tiktoken")


def test_hard_dependencies_are_the_real_modules_not_test_installed_stubs() -> None:
    """运行期断言：三个硬依赖在 sys.modules 里必须是真包，不是哪个测试塞的替身。"""
    import sys

    for name in _STUBBED_HARD_DEPS:
        module = sys.modules.get(name)
        if module is None:
            continue  # 本轮没人 import 它，谈不上污染
        origin = getattr(module, "__file__", None)
        assert origin, (
            f"sys.modules[{name!r}] 没有 __file__ —— 是测试塞进去的替身模块。"
            f"import 期改 sys.modules 会污染同一进程里后续所有测试（该目录恒 N failed，"
            f"单跑却全绿），禁止；{name} 是硬依赖，直接用真包。"
        )


def test_no_test_module_stubs_hard_dependencies_into_sys_modules() -> None:
    """源码扫描：整个 tests/ 树不得再出现「往 sys.modules 塞第三方硬依赖替身」。

    运行期断言只能抓到「本轮恰好被 import 过」的污染源；源码扫描抓的是模式本身，
    包括还没被任何一轮跑到的新增文件。
    """
    import re
    from pathlib import Path

    tests_root = Path(__file__).resolve().parent.parent
    pattern = re.compile(
        r"sys\.modules(?:\.setdefault\(|\[)\s*[\"'](" + "|".join(_STUBBED_HARD_DEPS) + r")[\"']"
    )
    offenders: list[str] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(tests_root.parent)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "禁止把第三方硬依赖的替身塞进 sys.modules（进程级副作用，跨文件污染）：\n"
        + "\n".join(offenders)
    )


def test_memory_consolidator_session_lock_is_strongly_retained(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )

    lock = consolidator.get_lock("session-1")
    lock_ref = weakref.ref(lock)
    del lock
    gc.collect()

    assert lock_ref() is not None
    assert consolidator.get_lock("session-1") is lock_ref()


def test_memory_consolidator_release_lock_drops_idle_session_lock(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )

    lock = consolidator.get_lock("session-1")

    assert consolidator.release_lock("session-1") is True
    assert consolidator.get_lock("session-1") is not lock


@pytest.mark.asyncio
async def test_memory_consolidator_release_lock_keeps_locked_session_lock(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )
    lock = consolidator.get_lock("session-1")

    await lock.acquire()
    try:
        assert consolidator.release_lock("session-1") is False
        assert consolidator.get_lock("session-1") is lock
    finally:
        lock.release()


@pytest.mark.asyncio
async def test_memory_consolidator_release_lock_keeps_lock_with_waiter(tmp_path) -> None:
    consolidator = MemoryConsolidator(
        tmp_path,
        provider=object(),
        model="demo",
        sessions=object(),
        context_window_tokens=100,
        build_messages=lambda **_kwargs: [],
        get_tool_definitions=lambda: [],
    )
    lock = consolidator.get_lock("session-1")

    await lock.acquire()
    waiter = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)

    lock.release()
    try:
        assert consolidator.release_lock("session-1") is False
        assert consolidator.get_lock("session-1") is lock
        await asyncio.wait_for(waiter, timeout=0.1)
        assert lock.locked()
    finally:
        if not waiter.done():
            waiter.cancel()
        if lock.locked():
            lock.release()


@pytest.mark.asyncio
async def test_agent_loop_new_releases_idle_memory_lock(tmp_path) -> None:
    from deeptutor.tutorbot.agent.loop import AgentLoop
    from deeptutor.tutorbot.bus.queue import MessageBus
    from deeptutor.tutorbot.providers.base import LLMProvider, LLMResponse

    class FakeProvider(LLMProvider):
        async def chat(self, *args, **kwargs) -> LLMResponse:
            return LLMResponse(content="unused")

        def get_default_model(self) -> str:
            return "fake-model"

    loop = AgentLoop(MessageBus(), FakeProvider(), tmp_path)
    session_key = "test:new"
    lock = loop.memory_consolidator.get_lock(session_key)

    result = await loop.process_direct("/new", session_key=session_key)

    assert result == "New session started."
    assert loop.memory_consolidator.get_lock(session_key) is not lock
