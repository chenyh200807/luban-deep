"""Root pytest fixtures: per-test isolation for process-level global state.

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

import pytest


@pytest.fixture(autouse=True)
def _isolate_external_auth_store(tmp_path_factory, monkeypatch):
    """Point external-auth users/sessions files at a writable per-test tmp dir.

    The production defaults are absolute container paths
    (``/app/data/user/external_auth`` and the legacy ``/root/luban/.storage``).
    A test that exercises external-auth writeback without overriding the path
    targets those prod paths — readable/writable on a developer machine whose
    .env points elsewhere, but a PermissionError on a hermetic CI runner that
    cannot touch ``/root`` or ``/app``. Default both files to tmp so no test
    writes outside its sandbox; tests that set their own override still win
    because their ``monkeypatch.setenv`` runs after this autouse fixture.
    """
    store_dir = tmp_path_factory.mktemp("external_auth_store")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(store_dir / "users.json"))
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", str(store_dir / "sessions.json"))


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
