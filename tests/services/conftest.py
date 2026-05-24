"""Shared fixtures for tests/services/.

Currently provides per-test isolation for module-level mutable state in
``deeptutor.services.question_lifecycle_skills`` so test ordering cannot
silently mask missing-skill warnings (post-review fix 2026-05-24, code-review
MEDIUM #2; symbol renamed to ``_MISSING_LOGGED`` after the hermes
edu-skills booster merge on origin/main).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_question_lifecycle_missing_logged():
    """Clear the once-per-process missing-skill warning set around each test.

    ``question_lifecycle_skills._MISSING_LOGGED`` is a process-level singleton
    designed to keep alert volume low in production (one warning per missing
    skill name per process). In tests this can hide regressions because a
    prior test that triggered a missing-skill warning will suppress the same
    warning in a later test that depends on it. Snapshot-restore around each
    test gives us back per-test isolation without changing production
    semantics.
    """
    from deeptutor.services import question_lifecycle_skills as mod

    saved = set(mod._MISSING_LOGGED)
    mod._MISSING_LOGGED.clear()
    try:
        yield
    finally:
        mod._MISSING_LOGGED.clear()
        mod._MISSING_LOGGED.update(saved)
