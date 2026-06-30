import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from deeptutor.logging import get_logger
from deeptutor.logging.context import (
    bind_log_context,
    bind_request_id,
    reset_log_context,
    reset_request_id,
)
from deeptutor.api.dependencies import require_admin, require_metrics_access
from deeptutor.api.runtime_metrics import (
    APIRuntimeMetrics,
    get_turn_runtime_metrics,
    render_prometheus_metrics,
)
from deeptutor.services.config import get_env_store
from deeptutor.services.branding import get_api_title, get_api_welcome_message
from deeptutor.services.learner_state.runtime import create_default_learner_state_runtime
from deeptutor.services.observability import get_release_lineage_snapshot, get_surface_event_store
from deeptutor.services.observability import get_control_plane_store, reset_control_plane_store
from deeptutor.services.observability.launch_readiness import build_launch_readiness_run
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment, runtime_environment
from deeptutor.utils.error_rate_tracker import get_tracker_snapshot
from deeptutor.utils.network.circuit_breaker import get_circuit_breaker_snapshot

# Note: Don't set service_prefix here - start_web.py already adds [Backend] prefix
logger = get_logger("API")


def _api_docs_enabled() -> bool:
    return env_flag("DEEPTUTOR_ENABLE_API_DOCS", default=not is_production_environment())


class _SuppressWsNoise(logging.Filter):
    """Suppress noisy uvicorn logs for WebSocket connection churn."""

    _SUPPRESSED = ("connection open", "connection closed")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(f in msg for f in self._SUPPRESSED)


logging.getLogger("uvicorn.error").addFilter(_SuppressWsNoise())

CONFIG_DRIFT_ERROR_TEMPLATE = (
    "Configuration Drift Detected: Capability tool references {drift} are not "
    "registered in the runtime tool registry. Register the missing tools or "
    "remove the stale tool names from the capability manifests."
)

_DEFAULT_DEV_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3782",
    "http://127.0.0.1:3782",
)
_DEFAULT_PRODUCTION_CORS_ORIGINS = (
    "https://www.yousenjiaoyu.com",
)
_READINESS_CHECK_NAMES = (
    "config_consistent",
    "llm_client_ready",
    "event_bus_ready",
    "tutorbots_ready",
    "learner_state_runtime_ready",
)

# Production-required secrets. Single source of truth shared with
# scripts/validate_aliyun_release_env.sh (deploy-time .env gate); this is the
# matching startup-time gate so a misconfigured production process fails fast
# instead of booting with auth disabled. Local/dev (non-production) is exempt so
# `make dev` keeps working without these set.
_PRODUCTION_REQUIRED_ENV_KEYS = (
    "DEEPTUTOR_AUTH_SECRET",
    "DEEPTUTOR_ADMIN_USER_IDS",
)


def _assessment_form_prewarm_enabled() -> bool:
    return (
        is_production_environment()
        or env_flag("ASSESSMENT_USE_SUPABASE", default=False)
        or env_flag("ASSESSMENT_PREWARM_FORMS", default=False)
    )


def _prewarm_assessment_forms_sync() -> None:
    try:
        from deeptutor.services.member_console import get_member_console_service

        result = get_member_console_service().prewarm_assessment_forms()
        logger.info(f"Assessment forms prewarmed: {result}")
    except Exception as exc:
        logger.warning(f"Failed to prewarm assessment forms: {exc}", exc_info=True)


class SafeOutputStaticFiles(StaticFiles):
    """Static file mount that only exposes explicitly whitelisted artifacts."""

    def __init__(self, *args, path_service, **kwargs):
        super().__init__(*args, **kwargs)
        self._path_service = path_service

    async def get_response(self, path: str, scope):
        if not self._path_service.is_public_output_path(path):
            raise HTTPException(status_code=404, detail="Output not found")
        return await super().get_response(path, scope)


def _default_cors_allow_origins() -> list[str]:
    if is_production_environment():
        return list(_DEFAULT_PRODUCTION_CORS_ORIGINS)
    return list(_DEFAULT_DEV_CORS_ORIGINS)


def _legacy_routers_enabled() -> bool:
    return env_flag(
        "DEEPTUTOR_ENABLE_LEGACY_ROUTERS",
        default=not is_production_environment(),
    )


def _startup_fail_fast_enabled() -> bool:
    return env_flag(
        "DEEPTUTOR_STARTUP_FAIL_FAST",
        default=is_production_environment(),
    )


def _public_outputs_enabled() -> bool:
    return env_flag(
        "DEEPTUTOR_ENABLE_PUBLIC_OUTPUTS",
        default=not is_production_environment(),
    )


def get_cors_allow_origins() -> list[str]:
    """Return the effective CORS origin allowlist used by the API app."""
    raw_allowlist = get_env_store().get("DEEPTUTOR_CORS_ALLOW_ORIGINS", "").strip()
    if not raw_allowlist:
        raw_allowlist = ",".join(
            value
            for value in (
                get_env_store().get("CORS_ORIGIN", "").strip(),
                get_env_store().get("CORS_ORIGINS", "").strip(),
            )
            if value
        )
    if raw_allowlist:
        origins: list[str] = []
        seen: set[str] = set()
        for origin in raw_allowlist.replace("\n", ",").split(","):
            candidate = origin.strip().rstrip("/")
            if not candidate or candidate == "*":
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            origins.append(candidate)
        if origins:
            return origins
        logger.warning(
            "DEEPTUTOR_CORS_ALLOW_ORIGINS did not contain any valid origins; falling back to defaults"
        )
    return _default_cors_allow_origins()


def _initial_readiness_checks() -> dict[str, bool]:
    return {name: False for name in _READINESS_CHECK_NAMES}


def _set_readiness_check(app: FastAPI, name: str, ready: bool) -> None:
    checks = getattr(app.state, "readiness_checks", None)
    if not isinstance(checks, dict):
        checks = _initial_readiness_checks()
    checks[name] = ready
    app.state.readiness_checks = checks
    app.state.readiness_ready = bool(checks) and all(checks.values())


def _configure_runtime_observability_store() -> None:
    configured_dir = str(os.getenv("DEEPTUTOR_OBSERVABILITY_STORE_DIR") or "").strip()
    if configured_dir:
        return
    runtime_store_dir = get_path_service().get_runtime_dir() / "observability" / "control_plane"
    reset_control_plane_store(base_dir=runtime_store_dir)


def _persist_launch_readiness_check(app: FastAPI) -> None:
    try:
        payload = build_launch_readiness_run(
            checks=getattr(app.state, "readiness_checks", {}) or {},
            release=get_release_lineage_snapshot(),
        )
        get_control_plane_store().write_run(
            kind="readiness_checks",
            run_id=str(payload.get("run_id") or ""),
            release_id=str((payload.get("release") or {}).get("release_id") or ""),
            payload=payload,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist launch readiness check: {exc}", exc_info=True)


def get_readyz_payload(app: FastAPI | None = None) -> tuple[int, dict[str, object]]:
    target_app = app or globals()["app"]
    checks = getattr(target_app.state, "readiness_checks", _initial_readiness_checks())
    if not isinstance(checks, dict):
        checks = _initial_readiness_checks()
    ready = bool(checks) and all(bool(value) for value in checks.values())
    payload = {
        "status": "ok" if ready else "degraded",
        "ready": ready,
        "checks": checks,
    }
    return (200 if ready else 503, payload)


def _is_placeholder_llm_endpoint(base_url: str | None) -> bool:
    raw = str(base_url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    placeholder_domains = ("example.com", "example.net", "example.org")
    return host.endswith(".example") or any(
        host == domain or host.endswith(f".{domain}") for domain in placeholder_domains
    )


def _validate_startup_llm_client(llm_client: object) -> None:
    config = getattr(llm_client, "config", None)
    endpoint = None
    if config is not None:
        endpoint = getattr(config, "effective_url", None) or getattr(config, "base_url", None)
    if _is_placeholder_llm_endpoint(endpoint):
        raise RuntimeError(
            "LLM endpoint points to a placeholder host; configure a real provider endpoint before startup"
        )


def assert_required_env() -> None:
    """Fail fast in production when canonical required secrets are absent.

    Mirrors the deploy-time check in scripts/validate_aliyun_release_env.sh so a
    production process never boots with auth misconfigured. Non-production
    environments (default "local") are intentionally exempt to keep local
    startup frictionless. Raises ``RuntimeError`` listing every missing key.
    """
    if not is_production_environment():
        return
    store = get_env_store()
    missing = [
        key
        for key in _PRODUCTION_REQUIRED_ENV_KEYS
        if not str(store.get(key, "") or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Production startup blocked: required environment variables are "
            "unset or empty: " + ", ".join(missing)
        )


def validate_tool_consistency():
    """
    Validate that capability manifests only reference tools that are actually
    registered in the runtime ``ToolRegistry``.
    """
    try:
        from deeptutor.runtime.registry.capability_registry import get_capability_registry
        from deeptutor.runtime.registry.tool_registry import get_tool_registry

        capability_registry = get_capability_registry()
        tool_registry = get_tool_registry()
        available_tools = set(tool_registry.list_tools())

        referenced_tools = set()
        for manifest in capability_registry.get_manifests():
            referenced_tools.update(manifest.get("tools_used", []) or [])
        if "web_search" in referenced_tools:
            from deeptutor.services.search import is_web_search_runtime_available

            if not is_web_search_runtime_available():
                referenced_tools.discard("web_search")

        drift = referenced_tools - available_tools
        if drift:
            raise RuntimeError(CONFIG_DRIFT_ERROR_TEMPLATE.format(drift=drift))
    except RuntimeError:
        logger.exception("Configuration validation failed")
        raise
    except Exception:
        logger.exception("Failed to load configuration for validation")
        raise


async def _start_learner_state_runtime(app: FastAPI) -> None:
    runtime = create_default_learner_state_runtime(get_path_service())
    app.state.learner_state_runtime = runtime
    await runtime.start()


async def _stop_learner_state_runtime(app: FastAPI) -> None:
    runtime = getattr(app.state, "learner_state_runtime", None)
    if runtime is None:
        return
    await runtime.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    Gracefully handle startup and shutdown events, avoid CancelledError
    """
    # Execute on startup
    logger.info("Application startup")
    app.state.readiness_checks = _initial_readiness_checks()
    app.state.readiness_ready = False
    startup_failures: list[str] = []

    # Validate configuration consistency
    validate_tool_consistency()
    _set_readiness_check(app, "config_consistent", True)

    # Initialize LLM client early so OPENAI_* env vars are available before
    # any downstream provider integrations start.
    try:
        from deeptutor.services.llm import get_llm_client

        llm_client = get_llm_client()
        _validate_startup_llm_client(llm_client)
        logger.info(f"LLM client initialized: model={llm_client.config.model}")
        _set_readiness_check(app, "llm_client_ready", True)
    except Exception as e:
        logger.warning(f"Failed to initialize LLM client at startup: {e}")
        startup_failures.append(f"llm_client_ready: {e}")

    try:
        from deeptutor.events.event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.start()
        logger.info("EventBus started")
        _set_readiness_check(app, "event_bus_ready", True)
    except Exception as e:
        logger.warning(f"Failed to start EventBus: {e}")
        startup_failures.append(f"event_bus_ready: {e}")

    # Self-heal orphaned turns left ``running`` by a previous crash (OOM /
    # SIGKILL). On restart the process has no in-memory turn tasks, so any
    # ``running`` row in SQLite is provably orphaned — its _run_turn finally
    # block never ran. Sweep them to ``failed`` once, before TutorBots start,
    # so global active/billing views are not polluted. Idempotent.
    try:
        from deeptutor.services.session import get_sqlite_session_store

        recovered = await get_sqlite_session_store().recover_all_orphaned_turns(
            "orphaned_on_restart"
        )
        logger.info(f"Recovered {recovered} orphaned running turn(s) on startup")
    except Exception as e:
        logger.warning(f"Failed to recover orphaned running turns at startup: {e}")

    try:
        from deeptutor.services.tutorbot import get_tutorbot_manager
        await get_tutorbot_manager().auto_start_bots()
        _set_readiness_check(app, "tutorbots_ready", True)
    except Exception as e:
        logger.warning(f"Failed to auto-start TutorBots: {e}")
        startup_failures.append(f"tutorbots_ready: {e}")

    # Production secret gate: route through the existing fail-fast mechanism so a
    # misconfigured production process aborts instead of serving with auth off.
    try:
        assert_required_env()
    except RuntimeError as e:
        logger.error(str(e))
        startup_failures.append(f"required_env: {e}")

    # Billing visibility: if production is serving with billing enforcement OFF, every
    # turn is free to the user and full-cost to the operator. That may be intentional
    # (beta), but it must never be a *silent* misconfiguration — emit a loud warning so
    # ops can see it in logs.
    try:
        from deeptutor.services.runtime_env import is_production_environment
        from deeptutor.services.wallet.service import is_billing_enforcement_enabled

        if is_production_environment() and not is_billing_enforcement_enabled():
            logger.warning(
                "BILLING ENFORCEMENT IS DISABLED IN PRODUCTION — every LLM turn is free to "
                "the user and full-cost to the operator. Set DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=true "
                "to charge, or confirm this is an intentional free-beta window."
            )
    except Exception:
        logger.debug("billing enforcement startup check skipped", exc_info=True)

    # Multi-worker safety visibility: the TutorBot heartbeat single-instance lock,
    # the per-user WS connection cap and cross-worker rate limits all coordinate
    # through the redis (valkey) backend. With UVICORN_WORKERS>1 and a non-redis
    # backend those guards silently degrade to per-process behavior (N× duplicate
    # heartbeats, N× connection caps) — loud warning, same pattern as billing above.
    try:
        workers = int(str(os.getenv("UVICORN_WORKERS", "1")).strip() or "1")
        rate_limit_backend = str(os.getenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")).strip().lower()
        redis_url = str(
            os.getenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or ""
        ).strip()
        if workers > 1 and (rate_limit_backend != "redis" or not redis_url):
            logger.warning(
                "UVICORN_WORKERS=%s but DEEPTUTOR_RATE_LIMIT_BACKEND=%s (redis url %s) — "
                "cross-worker guards (heartbeat single-instance lock, per-user WS connection "
                "cap) are DEGRADED to per-process behavior. Set DEEPTUTOR_RATE_LIMIT_BACKEND=redis "
                "and DEEPTUTOR_RATE_LIMIT_REDIS_URL=redis://valkey:6379/0 for multi-worker runs.",
                workers,
                rate_limit_backend or "unset",
                "set" if redis_url else "MISSING",
            )
    except Exception:
        logger.debug("multi-worker config consistency check skipped", exc_info=True)

    app.state.readiness_ready = bool(app.state.readiness_checks) and all(
        app.state.readiness_checks.values()
    )
    if startup_failures and _startup_fail_fast_enabled():
        raise RuntimeError(
            "Critical startup dependencies failed: " + "; ".join(startup_failures)
        )

    try:
        await _start_learner_state_runtime(app)
        logger.info("LearnerState runtime started")
        _set_readiness_check(app, "learner_state_runtime_ready", True)
    except Exception as e:
        logger.warning(f"Failed to start LearnerState runtime: {e}")
        startup_failures.append(f"learner_state_runtime: {e}")
        _set_readiness_check(app, "learner_state_runtime_ready", False)
        if _startup_fail_fast_enabled():
            raise RuntimeError(
                "Critical startup dependencies failed: " + "; ".join(startup_failures)
            )

    _configure_runtime_observability_store()
    _persist_launch_readiness_check(app)

    # Cross-worker metrics: each worker periodically dumps its metric bundle so a Prometheus
    # scrape on any worker merges every worker's view (avoids ~N× under-count with N workers).
    try:
        from deeptutor.runtime.safety import spawn_task as _spawn_task

        app.state.metrics_dump_task = _spawn_task(
            _metrics_dump_loop(), name="observability.metrics_dump"
        )
    except Exception as e:
        logger.warning(f"Failed to start cross-worker metrics dump loop: {e}")

    if _assessment_form_prewarm_enabled():
        from deeptutor.runtime.safety import spawn_task as _spawn_task
        app.state.assessment_form_prewarm_task = _spawn_task(
            asyncio.to_thread(_prewarm_assessment_forms_sync),
            name="startup.assessment_form_prewarm",
        )
        logger.info("Assessment form prewarm scheduled")
    yield

    # Execute on shutdown
    logger.info("Application shutdown")

    # Stop TutorBots
    try:
        from deeptutor.services.tutorbot import get_tutorbot_manager
        await get_tutorbot_manager().stop_all()
        logger.info("TutorBots stopped")
    except Exception as e:
        logger.warning(f"Failed to stop TutorBots: {e}")

    # Stop EventBus
    try:
        from deeptutor.events.event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.stop()
        logger.info("EventBus stopped")
    except Exception as e:
        logger.warning(f"Failed to stop EventBus: {e}")

    try:
        await _stop_learner_state_runtime(app)
        logger.info("LearnerState runtime stopped")
    except Exception as e:
        logger.warning(f"Failed to stop LearnerState runtime: {e}")

    # Stop the cross-worker metrics dump loop and remove this worker's file so a recreated
    # worker (new pid) does not leave a stale file lingering until it ages out.
    try:
        from deeptutor.services.observability import multiworker_metrics as _mwm

        task = getattr(app.state, "metrics_dump_task", None)
        if task is not None:
            task.cancel()
        _mwm.remove_worker_snapshot(get_path_service().get_observability_dir(), os.getpid())
    except Exception as e:
        logger.warning(f"Failed to stop metrics dump loop: {e}")


app = FastAPI(
    title=get_api_title(),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _api_docs_enabled() else None,
    redoc_url="/redoc" if _api_docs_enabled() else None,
    openapi_url="/openapi.json" if _api_docs_enabled() else None,
    # Disable automatic trailing slash redirects to prevent protocol downgrade issues
    # when deployed behind HTTPS reverse proxies (e.g., nginx).
    # Without this, FastAPI's 307 redirects may change HTTPS to HTTP.
    # See: https://github.com/HKUDS/DeepTutor/issues/112
    redirect_slashes=False,
)

app.state.readiness_checks = _initial_readiness_checks()
app.state.readiness_ready = False
app.state.runtime_metrics = APIRuntimeMetrics()

# SR6 PR-5: install HTTP exception envelope (HTTPException / RequestValidationError /
# unhandled Exception) — frozen {detail, request_id, error_code} contract.
# WS / streaming error semantics intentionally untouched (codex review R3).
from deeptutor.runtime.safety import (
    install_exception_handlers as _install_exc_handlers,
    register_readiness_check as _register_readiness_check,
)
_install_exc_handlers(app)


# SR6 PR-5: active readiness probes. The legacy `app.state.readiness_checks` static
# dict is a one-shot startup snapshot; these callbacks let /readyz reflect runtime
# drift (LLM key rotated to placeholder, SQLite file removed, etc.).

async def _check_llm_key_present() -> None:
    """Fail readiness if LLM_API_KEY / SUPABASE_KEY is a known placeholder value."""
    import os as _os
    placeholder_markers = ("sk-xxx", "placeholder", "your-api-key", "")
    key = (_os.getenv("LLM_API_KEY") or _os.getenv("SUPABASE_KEY") or "").strip().lower()
    if not key or key in placeholder_markers:
        raise RuntimeError("LLM/Supabase key looks like a placeholder")


async def _check_sqlite_session_db_writable() -> None:
    """Fail readiness if the canonical SQLite session DB path is unreadable."""
    import os as _os
    from pathlib import Path as _Path
    candidate = _os.getenv("DEEPTUTOR_SQLITE_SESSION_PATH") or "data/chat_history.db"
    path = _Path(candidate)
    # File presence is enough for readiness; deep probes (open + SELECT 1) belong to
    # a follow-up SR6-W1 check once we can pool the connection.
    if not path.exists():
        # Empty DB on cold start is OK if Supabase RAG handles it; warn only.
        # Treat as soft warning, not failure, to avoid false-positive 503.
        return


# Register at import time so they're available before lifespan startup.
_register_readiness_check(
    "llm_key_not_placeholder",
    _check_llm_key_present,
    replace=True,
)
_register_readiness_check(
    "sqlite_session_db",
    _check_sqlite_session_db_writable,
    replace=True,
)

@app.middleware("http")
async def selective_access_log(request, call_next):
    started_at = time.perf_counter()
    request_id, token = bind_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if response.status_code != 200:
            query_string = request.url.query
            request_path = request.url.path if not query_string else f"{request.url.path}?{query_string}"
            logger.info(
                f'{request.client.host if request.client else "-"} - "{request.method} {request_path} HTTP/{request.scope.get("http_version", "1.1")}" {response.status_code}',
                extra={"request_id": request_id},
            )
        route = getattr(request.scope.get("route"), "path", request.url.path)
        app.state.runtime_metrics.record_request(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_ms=(time.perf_counter() - started_at) * 1000.0,
        )
        return response
    except Exception:
        route = getattr(request.scope.get("route"), "path", request.url.path)
        app.state.runtime_metrics.record_request(
            method=request.method,
            route=route,
            status_code=500,
            duration_ms=(time.perf_counter() - started_at) * 1000.0,
        )
        raise
    finally:
        reset_request_id(token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    # With allow_credentials=True, pin methods/headers instead of "*": a wildcard here
    # turns any future origin misconfig into a full credentialed cross-origin surface.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Metrics-Token"],
)

# Mount a filtered view over user outputs.
# Only whitelisted artifact paths are readable through the static handler.
path_service = get_path_service()
user_dir = path_service.get_public_outputs_root()

# Initialize user directories on startup
try:
    from deeptutor.services.setup import init_user_directories

    init_user_directories()
except Exception:
    # Fallback: just create the main directory if it doesn't exist
    if not user_dir.exists():
        user_dir.mkdir(parents=True)

if _public_outputs_enabled():
    app.mount(
        "/api/outputs",
        SafeOutputStaticFiles(directory=str(user_dir), path_service=path_service),
        name="outputs",
    )
else:
    logger.info("Public output mount disabled; /api/outputs is not exposed in this environment")

# Import routers only after runtime settings are initialized.
# Some router modules load YAML settings at import time.
from deeptutor.api.routers import (
    agent_config,
    attachments,
    bi,
    co_writer,
    dashboard,
    guide,
    invite_test,
    knowledge,
    learner_signal,
    learning_brain,
    luban_preview,
    member,
    memory,
    mobile,
    notebook,
    observability,
    photo_answer,
    plugins_api,
    question,
    sessions,
    settings,
    solve,
    system,
    tutor_state,
    tutorbot,
    unified_ws,
    question_notebook,
)

# Include routers
if _legacy_routers_enabled():
    app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
    app.include_router(question.router, prefix="/api/v1/question", tags=["question"])
    app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(co_writer.router, prefix="/api/v1/co_writer", tags=["co_writer"])
    app.include_router(notebook.router, prefix="/api/v1/notebook", tags=["notebook"])
    app.include_router(guide.router, prefix="/api/v1/guide", tags=["guide"])
    app.include_router(plugins_api.router, prefix="/api/v1/plugins", tags=["plugins"])
    app.include_router(tutorbot.router, prefix="/api/v1/tutorbot", tags=["tutorbot"])
else:
    logger.info(
        "Legacy routers disabled; production contract remains on /api/v1/ws and authenticated REST APIs"
    )
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(invite_test.router, prefix="/api/v1/invite-test", tags=["invite-test"])
app.include_router(luban_preview.router, prefix="/api/v1/luban-preview", tags=["luban-preview"])
app.include_router(learner_signal.router, prefix="/api/v1/learner-signal", tags=["learner_signal"])
if runtime_environment() == "local" and env_flag("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", default=False):
    app.include_router(learning_brain.router, prefix="/api/v1/learning-brain", tags=["learning-brain"])

    @app.get("/wechat-harness", include_in_schema=False)
    async def learning_brain_wechat_harness():
        return HTMLResponse(learning_brain.render_learning_brain_harness_html())

app.include_router(member.router, prefix="/api/v1/member", tags=["member"])
app.include_router(bi.router, prefix="/api/v1/bi", tags=["bi"])
app.include_router(memory.router, prefix="/api/v1/memory", tags=["memory"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(question_notebook.router, prefix="/api/v1/question-notebook", tags=["question-notebook"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(agent_config.router, prefix="/api/v1/agent-config", tags=["agent-config"])
app.include_router(tutor_state.router, prefix="/api/v1/tutor-state", tags=["tutor-state"])
app.include_router(observability.router, prefix="/api/v1/observability", tags=["observability"])
# Photo-answer OCR input layer — feature-flagged (DEEPTUTOR_PHOTO_ANSWER_ENABLED,
# default off → endpoints 404). Plan: docs/plan/2026-06-10-luban-photo-answer-*.md
app.include_router(photo_answer.router, prefix="/api/v1/photo-answer", tags=["photo-answer"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["attachments"])

# Unified WebSocket endpoint
app.include_router(unified_ws.router, prefix="/api/v1", tags=["unified-ws"])


@app.get("/")
async def root():
    return {"message": get_api_welcome_message()}


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {
        "status": "ok",
        "alive": True,
        "uptime_seconds": app.state.runtime_metrics.snapshot()["uptime_seconds"],
    }


@app.get("/readyz", include_in_schema=False)
async def readyz():
    """SR6 PR-5: active probes via runtime safety registry + legacy static checks merged.

    Backwards-compat: any caller polling readiness still gets the existing
    static dict in `checks_static`. New active probes (SQLite ping, LLM
    placeholder check) live under `checks_active` and gate the overall status.
    """
    from deeptutor.runtime.safety import run_readiness_checks

    active = await run_readiness_checks()
    status_code, payload = get_readyz_payload(app)
    body = dict(payload) if isinstance(payload, dict) else {"payload": payload}
    body["checks_active"] = active
    if any(v != "ok" for v in active.values()):
        status_code = 503
        body["ready"] = False
    return JSONResponse(status_code=status_code, content=body)


def _build_live_metric_bundle() -> dict:
    """This worker's five per-process singleton snapshots, bundled for cross-worker merge.
    These same singletons also feed the JSON ``/metrics`` and observer rollups, so the
    multiworker fix reads them rather than re-instrumenting the hot path."""
    return {
        "http": app.state.runtime_metrics.snapshot(),
        "turn": get_turn_runtime_metrics().snapshot(),
        "surface": get_surface_event_store().snapshot(),
        "providers": get_tracker_snapshot(),
        "circuit_breakers": get_circuit_breaker_snapshot(),
    }


async def _metrics_dump_loop() -> None:
    """Periodically persist this worker's metric bundle to the shared observability dir so
    a Prometheus scrape landing on any worker can merge every worker's view (UVICORN_WORKERS>1
    otherwise under-counts ~N×). Off the hot path; a dump failure is logged, never fatal."""
    from deeptutor.services.observability import multiworker_metrics as _mwm

    pid = os.getpid()
    while True:
        try:
            base = get_path_service().get_observability_dir()
            _mwm.dump_worker_snapshot(base, pid, _build_live_metric_bundle())
        except Exception:
            logger.debug("worker metrics dump failed", exc_info=True)
        try:
            await asyncio.sleep(_mwm.DEFAULT_DUMP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break


@app.get("/metrics", include_in_schema=False, dependencies=[Depends(require_metrics_access)])
async def metrics():
    return {
        "release": get_release_lineage_snapshot(),
        "http": app.state.runtime_metrics.snapshot(),
        "turn_runtime": get_turn_runtime_metrics().snapshot(),
        "surface_events": get_surface_event_store().snapshot(),
        "readiness": get_readyz_payload(app)[1],
        "providers": {
            "error_rates": get_tracker_snapshot(),
            "circuit_breakers": get_circuit_breaker_snapshot(),
        },
    }


@app.get("/metrics/prometheus", include_in_schema=False, dependencies=[Depends(require_metrics_access)])
async def metrics_prometheus():
    from deeptutor.services.observability import multiworker_metrics as _mwm

    # Merge every worker's snapshot (this worker's live + the others' fresh files) so a
    # scrape is correct under UVICORN_WORKERS>1. Fail-safe: an observability endpoint must
    # never 500 — on any merge error fall back to this worker's live (per-worker) view.
    live_bundle = _build_live_metric_bundle()
    try:
        merged = _mwm.collect_merged_snapshots(
            get_path_service().get_observability_dir(), os.getpid(), live_bundle
        )
    except Exception:
        logger.debug("cross-worker metrics merge failed; serving live worker only", exc_info=True)
        merged = live_bundle

    # Readiness and release lineage are per-worker-consistent, so the live worker's values
    # are authoritative — they are not part of the cross-worker merge.
    readiness_snapshot = get_readyz_payload(app)[1]
    release_snapshot = get_release_lineage_snapshot()
    return PlainTextResponse(
        render_prometheus_metrics(
            http_snapshot=merged["http"],
            turn_snapshot=merged["turn"],
            surface_snapshot=merged["surface"],
            readiness_snapshot=readiness_snapshot,
            provider_error_rates=merged["providers"],
            circuit_breakers=merged["circuit_breakers"],
            release_snapshot=release_snapshot,
        ),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


if __name__ == "__main__":
    from deeptutor.api.run_server import main as run_server_main

    run_server_main()
