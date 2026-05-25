"""Unit tests for SR6 PR-5 runtime safety primitives."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from deeptutor.runtime.safety import (
    clear_readiness_checks,
    install_exception_handlers,
    register_readiness_check,
    run_readiness_checks,
    spawn_task,
)


@pytest.fixture(autouse=True)
def _isolate_readiness_registry():
    clear_readiness_checks()
    yield
    clear_readiness_checks()


class TestSpawnTask:
    @pytest.mark.asyncio
    async def test_spawn_task_runs_coroutine(self) -> None:
        ran = asyncio.Event()

        async def _coro() -> None:
            ran.set()

        task = spawn_task(_coro(), name="unit_ok")
        await asyncio.wait_for(task, timeout=1.0)
        assert ran.is_set()

    @pytest.mark.asyncio
    async def test_spawn_task_default_on_error_logs(self, caplog) -> None:
        async def _boom() -> None:
            raise ValueError("intentional")

        task = spawn_task(_boom(), name="unit_boom")
        with pytest.raises(ValueError):
            await task
        # done_callback runs after await; give the loop one tick.
        await asyncio.sleep(0)
        # logger.exception was called — we expect at least one "background failure" record.
        assert any("spawn_task background failure" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_spawn_task_custom_on_error_fires(self) -> None:
        captured: list[BaseException] = []

        async def _boom() -> None:
            raise RuntimeError("nope")

        task = spawn_task(_boom(), name="unit_on_err", on_error=captured.append)
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)
        assert len(captured) == 1
        assert isinstance(captured[0], RuntimeError)


class TestReadinessRegistry:
    @pytest.mark.asyncio
    async def test_run_empty_registry(self) -> None:
        result = await run_readiness_checks()
        assert result == {}

    @pytest.mark.asyncio
    async def test_register_and_run_all_ok(self) -> None:
        async def _ok() -> None:
            return None

        register_readiness_check("ok_a", _ok)
        register_readiness_check("ok_b", _ok)
        result = await run_readiness_checks()
        assert result == {"ok_a": "ok", "ok_b": "ok"}

    @pytest.mark.asyncio
    async def test_failing_check_reports_reason(self) -> None:
        async def _bad() -> None:
            raise ValueError("boom")

        register_readiness_check("bad", _bad)
        result = await run_readiness_checks()
        assert result["bad"].startswith("fail: ValueError")

    @pytest.mark.asyncio
    async def test_slow_check_times_out(self) -> None:
        async def _slow() -> None:
            await asyncio.sleep(5)  # exceeds 1.5s timeout

        register_readiness_check("slow", _slow)
        result = await run_readiness_checks()
        assert result["slow"] == "fail: timeout"

    def test_duplicate_registration_raises(self) -> None:
        async def _x() -> None:
            return None

        register_readiness_check("dup", _x)
        with pytest.raises(ValueError, match="already registered"):
            register_readiness_check("dup", _x)

    @pytest.mark.asyncio
    async def test_explicit_replace_allows_reloadable_app_checks(self) -> None:
        async def _old() -> None:
            raise RuntimeError("old")

        async def _new() -> None:
            return None

        register_readiness_check("reloadable", _old)
        register_readiness_check("reloadable", _new, replace=True)

        result = await run_readiness_checks()
        assert result == {"reloadable": "ok"}


class TestExceptionEnvelope:
    def _build_app(self) -> FastAPI:
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/raise_http")
        async def raise_http():
            raise HTTPException(status_code=404, detail="not found")

        @app.get("/raise_unhandled")
        async def raise_unhandled():
            raise RuntimeError("kaboom")

        return app

    def test_http_exception_envelope(self) -> None:
        client = TestClient(self._build_app())
        resp = client.get("/raise_http")
        assert resp.status_code == 404
        body = resp.json()
        assert set(body.keys()) == {"detail", "request_id", "error_code"}
        assert body["detail"] == "not found"
        assert body["error_code"] == "http_404"
        assert body["request_id"]  # non-empty (uuid hex)

    def test_unhandled_exception_envelope(self) -> None:
        client = TestClient(self._build_app(), raise_server_exceptions=False)
        resp = client.get("/raise_unhandled")
        assert resp.status_code == 500
        body = resp.json()
        assert set(body.keys()) == {"detail", "request_id", "error_code"}
        # Default (non-DEBUG): generic message, no stack trace leak
        assert body["detail"] == "internal_error"
        assert body["error_code"] == "internal_error"
