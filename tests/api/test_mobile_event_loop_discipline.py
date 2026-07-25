"""病B-4 事件循环纪律回归测试。

含同步账本锁读 / 同步 Supabase 读的 mobile read-model 端点必须是同步 ``def``
(FastAPI 自动走线程池),禁止 ``async def`` 直接在事件循环上跑同步 IO。

背景(2026-07-05 学习页加载慢根因):``/homepage/dashboard`` 曾是 ``async def``
直调 ``member_service.get_home_dashboard``(内含 ``_load_member_snapshot`` 账本
锁读 + ``read_snapshot``/``read_compiled_learning_truth`` 同步 Supabase 读,
live 实测单请求 3-5s)。事件循环被占死时,同 worker 的轻请求被饿死——live 探针:
并发 3 个 dashboard 期间 ``/luban/lessons`` 从 0.13s 涨到 7.2s。

同类端点若把 ``def`` 改回 ``async def``,本测试即红。

2026-07-25 扩展:同一条纪律在 BI 读路径上以**另一种形状**复发。BI 不能照搬
"端点降同步 ``def``"——``BIService`` 有真 ``httpx.AsyncClient`` 调用,整链降级
会引入 ``asyncio.run`` 边界。BI 采用的是等价的另一半:端点保持 ``async``,但把
同步工作沉进 ``asyncio.to_thread``(与 ``sqlite_store._run_read`` 同范式)。
两种形状的**不变量是同一个**,所以守卫留在同一个文件里,不另起第二套权威。

形状检查(端点是不是 coroutine)对 BI 无效,因此下面第二个测试直接断言**行为**:
重读路径执行期间事件循环必须继续 tick。把 ``to_thread`` 去掉即红。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from deeptutor.api.routers import bi, member, mobile
from deeptutor.services.bi_service import BIService, _BiContext

# 已知内含同步账本/Supabase 读、必须走线程池的 GET read-model 端点。
# 形状是 (router 名, router, path) —— 这条纪律不是 mobile 专有的,新 router 直接
# 加进这张表,**不要另起一个 test_<router>_event_loop_discipline.py**:两份白名单
# 必然漂移,那正是 AGENTS §Single Authority Hard Gate 禁止的第二套权威。
_SYNC_REQUIRED_ROUTES: tuple[tuple[str, Any, str], ...] = (
    ("mobile", mobile.router, "/homepage/dashboard"),
    ("mobile", mobile.router, "/plan/mastery-dashboard"),
    ("mobile", mobile.router, "/bi/radar/{user_id}"),
    # 2026-07-25:这两条调的是同一个 3-5s 家族的 `get_dashboard`,2026-07-05 那轮
    # 只改了 mobile 的三条,它们被漏下,于是同一个病在别的 router 上原样存活。
    ("bi", bi.router, "/member/dashboard"),
    ("member", member.router, "/dashboard"),
)


def test_heavy_sync_read_model_routes_stay_off_event_loop() -> None:
    missing: list[str] = []
    offenders: list[str] = []
    for module_name, router, path in _SYNC_REQUIRED_ROUTES:
        endpoint = next(
            (r.endpoint for r in router.routes if getattr(r, "path", "") == path),
            None,
        )
        if endpoint is None:
            missing.append(f"{module_name}:{path}")
        elif asyncio.iscoroutinefunction(endpoint):
            offenders.append(f"{module_name}:{path}")

    assert not missing, f"expected routes not found: {sorted(missing)}"
    assert not offenders, (
        f"{sorted(offenders)} must be sync `def` endpoints (threadpool, 病B-4): they "
        "perform synchronous ledger/Supabase reads and would starve the event loop as "
        "`async def`."
    )


# --- BI 读路径:同一条纪律,另一种形状 ---------------------------------------

# 让被沉入线程池的同步工作明显长于事件循环的 tick 间隔,这样"没沉下去"和
# "沉下去了"在测量上相差一个数量级,不靠紧公差取胜。
_BLOCKING_SCAN_SECONDS = 0.30
_MAX_TOLERATED_STALL_SECONDS = 0.15


class _NoMemberService:
    """BI 只需要会员列表这一个能力;这里返回空集以便把变量隔离到阻塞行为上。"""

    def list_members_for_bi(self) -> list[dict[str, Any]]:
        return []


def _empty_context() -> _BiContext:
    return _BiContext(
        sessions=[],
        turns=[],
        result_events=[],
        tool_events=[],
        notebook_entries=[],
    )


def test_bi_read_path_keeps_the_event_loop_ticking() -> None:
    """BI 的重读路径执行期间,事件循环必须继续调度别的协程。

    这是病B-4 在 BI 上的行为化断言:``_load_business_context`` 内部是纯同步的
    SQLite 扫描 + 阻塞式会员目录 HTTP。若它们回到事件循环上直接跑(即去掉
    ``asyncio.to_thread``),同 worker 的其它请求——包括 TutorBot 流式——会被饿死
    整整一次扫描的时长。
    """
    service = BIService(member_service=_NoMemberService())

    def _blocking_scan(window_start: float) -> _BiContext:
        time.sleep(_BLOCKING_SCAN_SECONDS)
        return _empty_context()

    service._load_context_since = _blocking_scan  # type: ignore[method-assign]
    service._load_all_members = list  # type: ignore[method-assign]

    async def _scenario() -> float:
        worst_stall = 0.0
        finished = False

        async def _tick() -> None:
            nonlocal worst_stall
            last = time.perf_counter()
            while not finished:
                await asyncio.sleep(0.005)
                now = time.perf_counter()
                worst_stall = max(worst_stall, now - last)
                last = now

        ticker = asyncio.create_task(_tick())
        # `create_task` 只是排程。必须先让 ticker 真正跑起来并建立基线间隔,
        # 否则它会在阻塞结束之后才第一次执行,测量到 0 停顿——一个恒绿的假测试。
        await asyncio.sleep(0.05)
        await service._load_business_context(7)
        finished = True
        await ticker
        return worst_stall

    stall = asyncio.run(_scenario())
    assert stall < _MAX_TOLERATED_STALL_SECONDS, (
        f"event loop stalled {stall:.3f}s while BI loaded its business context "
        f"(blocking work was {_BLOCKING_SCAN_SECONDS:.2f}s). The synchronous scan / "
        "member-directory HTTP must run via asyncio.to_thread, not on the loop."
    )
