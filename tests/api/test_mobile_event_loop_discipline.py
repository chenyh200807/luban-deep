"""病B-4 事件循环纪律回归测试。

含同步账本锁读 / 同步 Supabase 读的 mobile read-model 端点必须是同步 ``def``
(FastAPI 自动走线程池),禁止 ``async def`` 直接在事件循环上跑同步 IO。

背景(2026-07-05 学习页加载慢根因):``/homepage/dashboard`` 曾是 ``async def``
直调 ``member_service.get_home_dashboard``(内含 ``_load_member_snapshot`` 账本
锁读 + ``read_snapshot``/``read_compiled_learning_truth`` 同步 Supabase 读,
live 实测单请求 3-5s)。事件循环被占死时,同 worker 的轻请求被饿死——live 探针:
并发 3 个 dashboard 期间 ``/luban/lessons`` 从 0.13s 涨到 7.2s。

同类端点若把 ``def`` 改回 ``async def``,本测试即红。
"""
from __future__ import annotations

import asyncio

from deeptutor.api.routers import mobile

# 已知内含同步账本/Supabase 读、必须走线程池的 GET read-model 端点。
_SYNC_REQUIRED_PATHS = {
    "/homepage/dashboard",
    "/plan/mastery-dashboard",
    "/bi/radar/{user_id}",
}


def test_heavy_sync_read_model_routes_stay_off_event_loop() -> None:
    seen: dict[str, object] = {}
    for route in mobile.router.routes:
        path = getattr(route, "path", "")
        if path in _SYNC_REQUIRED_PATHS:
            seen[path] = route.endpoint

    missing = _SYNC_REQUIRED_PATHS - set(seen)
    assert not missing, f"expected routes not found on mobile router: {sorted(missing)}"

    for path, endpoint in seen.items():
        assert not asyncio.iscoroutinefunction(endpoint), (
            f"{path} must be a sync `def` endpoint (threadpool, 病B-4): it performs "
            "synchronous ledger/Supabase reads and would starve the event loop as "
            "`async def`."
        )
