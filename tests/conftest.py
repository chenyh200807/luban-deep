"""Root pytest configuration.

`is_production_environment()` is fail-closed: an unset / unknown environment is
treated as production so dev-only safeguards never default to "open". The test
suite must therefore declare its environment explicitly. We default the whole
process to ``local`` at import time (before any test module — e.g.
``attempt_refs`` — is collected and runs its import-time secret check) so that:

* AGENTS §264 dev/QA login + mock-code paths stay exercised, and
* tests that rely on the historical non-production default keep passing.

Individual tests that need production behaviour still override this via
``monkeypatch.setenv("DEEPTUTOR_ENV", "production")`` (or ``delenv`` to assert the
fail-closed default).
"""

from __future__ import annotations

import os

import pytest

# setdefault, not a hard set: an outer harness can still force a production-mode
# test run by exporting DEEPTUTOR_ENV before invoking pytest.
os.environ.setdefault("DEEPTUTOR_ENV", "local")


@pytest.fixture(scope="session", autouse=True)
def _isolate_observer_event_dir(tmp_path_factory):
    """Redirect the observer turn-event log to a per-session tmp dir.

    Without this, tests that drive a full turn write turn_observation events into
    the PRODUCTION DEFAULT log dir (tmp/observability/observer/events/). Those
    events are ``test_only=False`` purely because their session ids do not happen
    to contain the fragile "shadow" heuristic token, so the control-plane
    shadow-hit counter counts pytest-fixture traffic as "verified clean
    production turns" — a coverage-inflation false-green.

    Fix at the root boundary (single authority): set
    ``DEEPTUTOR_OBSERVER_EVENT_DIR`` and re-point the singleton via
    ``reset_turn_event_log(events_dir=...)`` for the whole session, before any
    ``TurnEventLog`` is instantiated. The production default log then only ever
    contains real production turns, and the local counter honestly reports
    NOT-MEASURED (exit 2) until the instrumentation is actually deployed.

    Function-scoped tests that set their own ``reset_turn_event_log(events_dir=
    tmp_path)`` still override this within their scope — no conflict.
    """
    from deeptutor.services.observability import reset_turn_event_log

    events_dir = tmp_path_factory.mktemp("observer_events")
    previous = os.environ.get("DEEPTUTOR_OBSERVER_EVENT_DIR")
    os.environ["DEEPTUTOR_OBSERVER_EVENT_DIR"] = str(events_dir)
    reset_turn_event_log(events_dir=events_dir)
    try:
        yield events_dir
    finally:
        if previous is None:
            os.environ.pop("DEEPTUTOR_OBSERVER_EVENT_DIR", None)
        else:
            os.environ["DEEPTUTOR_OBSERVER_EVENT_DIR"] = previous
        reset_turn_event_log()
