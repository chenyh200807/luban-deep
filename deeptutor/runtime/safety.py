"""Project-level resilience primitives — SR6-P0 single source of truth for async safety.

PR-5 ships P0 subset only (codex review R3): spawn_task / readiness registry /
HTTP-only exception envelope. BoundedQueue is **intentionally not in P0** —
applying it to subscriber/event-bus channels without first defining per-channel
backpressure policy can silently drop user-visible LLM tokens. That work is
deferred to W1 with a channel matrix + slow-consumer pressure test.

What this file owns:
- ``spawn_task(coro, *, name, on_error)`` — replaces bare ``asyncio.create_task``.
  Default callback on failure is ``logger.exception``; pass ``on_error`` to
  override (e.g., pop a subscriber dict slot).
- ``register_readiness_check(name, check)`` — module-import-time registry.
  Replaces the previous ``app.state.readiness_checks`` static dict so ``/readyz``
  can actually re-probe dependencies (SQLite, LLM key placeholder, ...).
- ``run_readiness_checks()`` — parallel runner with per-check 1.5s timeout.
- ``install_exception_handlers(app)`` — frozen 3-field envelope
  ``{detail, request_id, error_code}`` for HTTPException / RequestValidationError /
  unhandled Exception. **Does NOT install a WebSocket-side handler** — WS errors
  keep their existing close-code / send_json semantics; that path is unified
  separately under the SR1 ``secure_ws_endpoint`` helper.

CI gate:
- ``scripts/ci/check_runtime_safety_usage.sh`` — main.py must call
  ``install_exception_handlers(app)`` + at least one ``register_readiness_check(``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_READINESS_TIMEOUT_SECONDS = 1.5
_ENVELOPE_FIELDS = ("detail", "request_id", "error_code")  # frozen contract


# ---------------------------------------------------------------------------
# 1) spawn_task — replaces bare asyncio.create_task
# ---------------------------------------------------------------------------

def spawn_task(
    coro: Awaitable[Any],
    *,
    name: str | None = None,
    on_error: Callable[[BaseException], None] | None = None,
) -> asyncio.Task[Any]:
    """``asyncio.create_task`` with a mandatory done-callback.

    Default behavior on failure: ``logger.exception`` with task name + exc.
    Pass ``on_error`` to override (e.g., to also pop a dict slot when a
    subscriber forward task dies).

    ``on_error`` is sync — for async cleanup, put it inside the coroutine's
    own ``try/finally`` and use ``on_error`` only for synchronous bookkeeping.
    """
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task[Any]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is None:
            return
        if on_error is not None:
            try:
                on_error(exc)
            except Exception:
                logger.exception("spawn_task on_error raised for task=%s", name)
            return
        logger.exception(
            "spawn_task background failure (name=%s)", name, exc_info=exc
        )

    task.add_done_callback(_done)
    return task


# ---------------------------------------------------------------------------
# 2) Readiness registry — callable checks, parallel runner
# ---------------------------------------------------------------------------

_READINESS_REGISTRY: dict[str, Callable[[], Awaitable[None]]] = {}


def register_readiness_check(
    name: str,
    check: Callable[[], Awaitable[None]],
    *,
    replace: bool = False,
) -> None:
    """Register at import / startup time.

    Order-independent; overwrite is an error unless ``replace=True`` is
    explicit. App modules that are deliberately reloadable in tests may replace
    their own checks while ad-hoc duplicate names still fail closed by default.

    The ``check`` callable should ``raise`` on failure and return None on success.
    It will be wrapped with a 1.5s timeout by ``run_readiness_checks``.
    """
    if name in _READINESS_REGISTRY and not replace:
        raise ValueError(f"readiness check already registered: {name}")
    _READINESS_REGISTRY[name] = check


def clear_readiness_checks() -> None:
    """Test helper — clears the registry. Production code never calls this."""
    _READINESS_REGISTRY.clear()


async def run_readiness_checks() -> dict[str, str]:
    """Run all registered checks in parallel with 1.5s timeout each.

    Returns ``{name: "ok" | "fail: <reason>"}``. Never raises.
    """
    names = list(_READINESS_REGISTRY)

    async def _one(n: str) -> tuple[str, str]:
        try:
            await asyncio.wait_for(
                _READINESS_REGISTRY[n](), timeout=_READINESS_TIMEOUT_SECONDS
            )
            return n, "ok"
        except asyncio.TimeoutError:
            return n, "fail: timeout"
        except Exception as exc:  # noqa: BLE001 — readiness reports all failures
            return n, f"fail: {type(exc).__name__}: {exc}"

    results = await asyncio.gather(*(_one(n) for n in names))
    return dict(results)


# ---------------------------------------------------------------------------
# 3) Exception envelope (HTTP only)
# ---------------------------------------------------------------------------

_DEBUG = os.getenv("DEEPTUTOR_DEBUG_ERRORS", "").strip().lower() in ("1", "true")


def _envelope(detail: str, request_id: str, error_code: str) -> dict[str, str]:
    """Build the frozen 3-field envelope. Field set is intentionally locked —
    extending the body means a contract change, not a quick patch."""
    return {"detail": detail, "request_id": request_id, "error_code": error_code}


def install_exception_handlers(app: FastAPI) -> None:
    """Single authority for 4xx / 5xx HTTP response shape. Idempotent.

    Does NOT install a WebSocket-side handler (codex R3): WS streaming has its
    own close-code / send_json error protocol and must not be unified with the
    HTTP envelope without first migrating ws_error helpers.
    """

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or uuid.uuid4().hex
        # 结构化 detail(dict/list)原样透传——str()化会把 {'error': code} 变成
        # 单引号字符串, 前端解析不到错误码, 把治理性 409/422 误当网络错误无限
        # 转圈(2026-07-12 首跑'保存中'卡死的根因)。契约 {detail, request_id,
        # error_code} 形状不变, detail 类型忠实于 raise 方。
        detail = exc.detail if isinstance(exc.detail, (dict, list)) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(detail, rid, f"http_{exc.status_code}"),
        )

    @app.exception_handler(RequestValidationError)
    async def _val_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or uuid.uuid4().hex
        return JSONResponse(
            status_code=422,
            content=_envelope(
                f"validation_error: {exc.errors()}", rid, "validation_error"
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "") or uuid.uuid4().hex
        logger.exception(
            "unhandled exception request_id=%s path=%s", rid, request.url.path
        )
        detail = (
            f"{type(exc).__name__}: {exc}" if _DEBUG else "internal_error"
        )
        return JSONResponse(
            status_code=500, content=_envelope(detail, rid, "internal_error")
        )
