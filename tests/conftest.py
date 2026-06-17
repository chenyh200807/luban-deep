"""Root pytest configuration and fixtures.

`is_production_environment()` is fail-closed: an unset / unknown environment is
treated as production so dev-only safeguards never default to "open". The test
suite must therefore declare its environment explicitly. We default the whole
process to ``local`` at import time (before any test module is collected) so
that dev/QA paths stay exercised. Individual tests that need production
behaviour still override this via ``monkeypatch``.

Several modules keep deliberately process-wide state (a path singleton, the
logging context-vars). That is correct for production — one process, one
runtime — but it makes test outcomes order-dependent: a test that leaves the
state mutated silently changes what a later test sees. When the suite is run
as a hermetic full tree (CI smoke = full ``pytest tests/``) those latent
cross-test leaks surface as failures that pass in isolation.

These autouse fixtures reset that shared state at each test boundary so every
test is reentrant regardless of run order, without touching production
semantics. Mirrors the narrower precedent in ``tests/services/conftest.py``.
"""

from __future__ import annotations

import os

import pytest

# setdefault, not a hard set: an outer harness can still force a production-mode
# test run by exporting DEEPTUTOR_ENV before invoking pytest.
os.environ.setdefault("DEEPTUTOR_ENV", "local")


@pytest.fixture(autouse=True)
def _reset_path_service_singleton():
    """Reset the ``PathService`` process singleton around each test.

    ``PathService`` resolves ``DEEPTUTOR_USER_DATA_DIR`` once at first
    instantiation and caches it for the whole process. A test that sets that
    env var (via monkeypatch) and triggers ``get_path_service()`` builds the
    singleton against a tmp dir; monkeypatch later restores the env, but the
    already-constructed singleton survives and pollutes any later test that
    asserts the default runtime paths.
    """
    from deeptutor.services.path_service import PathService

    PathService.reset_instance()
    try:
        yield
    finally:
        PathService.reset_instance()


@pytest.fixture(autouse=True)
def _reset_log_context_vars():
    """Clear the logging context-vars after each test.

    ``deeptutor.logging.context`` binds request/user/session/turn ids into
    ContextVars. A test that binds context at top level (not inside a request
    task with its own context copy) and forgets to call ``reset_log_context``
    leaks the value into the main thread's context, so a later test reading
    ``get_log_context()`` sees the stale id instead of the default "".
    Resetting to the empty default after each test stops leaks from
    propagating forward (snapshot-restore would re-apply an inherited leak).
    """
    from deeptutor.logging import context as log_context

    def _clear() -> None:
        for context_var in log_context._CONTEXT_VARS.values():
            context_var.set("")

    _clear()
    try:
        yield
    finally:
        _clear()
