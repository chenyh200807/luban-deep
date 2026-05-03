import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from deeptutor.services.path_service import get_path_service
from deeptutor.services.runtime_env import env_flag, is_production_environment
from deeptutor.utils.error_rate_tracker import get_tracker_snapshot
from deeptutor.utils.network.circuit_breaker import get_circuit_breaker_snapshot

# Note: Don't set service_prefix here - start_web.py already adds [Backend] prefix
logger = get_logger("API")


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
_READINESS_CHECK_NAMES = (
    "config_consistent",
    "llm_client_ready",
    "event_bus_ready",
    "tutorbots_ready",
    "learner_state_runtime_ready",
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
        logger.info("Assessment forms prewarmed: %s", result)
    except Exception as exc:
        logger.warning("Failed to prewarm assessment forms: %s", exc, exc_info=True)


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
        return []
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
    if raw_allowlist:
        origins: list[str] = []
        seen: set[str] = set()
        for origin in raw_allowlist.split(","):
            candidate = origin.strip()
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

    try:
        from deeptutor.services.tutorbot import get_tutorbot_manager
        await get_tutorbot_manager().auto_start_bots()
        _set_readiness_check(app, "tutorbots_ready", True)
    except Exception as e:
        logger.warning(f"Failed to auto-start TutorBots: {e}")
        startup_failures.append(f"tutorbots_ready: {e}")

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

    if _assessment_form_prewarm_enabled():
        app.state.assessment_form_prewarm_task = asyncio.create_task(
            asyncio.to_thread(_prewarm_assessment_forms_sync)
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


app = FastAPI(
    title=get_api_title(),
    version="1.0.0",
    lifespan=lifespan,
    # Disable automatic trailing slash redirects to prevent protocol downgrade issues
    # when deployed behind HTTPS reverse proxies (e.g., nginx).
    # Without this, FastAPI's 307 redirects may change HTTPS to HTTP.
    # See: https://github.com/HKUDS/DeepTutor/issues/112
    redirect_slashes=False,
)

app.state.readiness_checks = _initial_readiness_checks()
app.state.readiness_ready = False
app.state.runtime_metrics = APIRuntimeMetrics()

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
    allow_methods=["*"],
    allow_headers=["*"],
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
    bi,
    chat,
    co_writer,
    dashboard,
    guide,
    knowledge,
    member,
    memory,
    mobile,
    notebook,
    observability,
    plugins_api,
    question,
    sessions,
    settings,
    solve,
    system,
    tutor_state,
    tutorbot,
    unified_ws,
    vision_solver,
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
app.include_router(vision_solver.router, prefix="/api/v1", tags=["vision-solver"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])

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
    status_code, payload = get_readyz_payload(app)
    return JSONResponse(status_code=status_code, content=payload)


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
    http_snapshot = app.state.runtime_metrics.snapshot()
    turn_snapshot = get_turn_runtime_metrics().snapshot()
    surface_snapshot = get_surface_event_store().snapshot()
    readiness_snapshot = get_readyz_payload(app)[1]
    provider_error_rates = get_tracker_snapshot()
    circuit_breakers = get_circuit_breaker_snapshot()
    release_snapshot = get_release_lineage_snapshot()
    return PlainTextResponse(
        render_prometheus_metrics(
            http_snapshot=http_snapshot,
            turn_snapshot=turn_snapshot,
            surface_snapshot=surface_snapshot,
            readiness_snapshot=readiness_snapshot,
            provider_error_rates=provider_error_rates,
            circuit_breakers=circuit_breakers,
            release_snapshot=release_snapshot,
        ),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


if __name__ == "__main__":
    from deeptutor.api.run_server import main as run_server_main

    run_server_main()
