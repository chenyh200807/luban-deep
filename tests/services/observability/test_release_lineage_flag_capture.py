"""Capture-pattern coverage for release-lineage feature-flag snapshotting.

These assert that the highest-leverage engine-level gray-release flags
(`*_STAGE`, `SUPABASE_RAG_*`, `ASSESSMENT_*`, `QUESTION_LIFECYCLE_*`,
`*ACTION_LOOP*`) are captured into the ff_snapshot, so release lineage does
not silently drop the switches that actually move runtime behaviour.
"""

from __future__ import annotations

import pytest

from deeptutor.services.observability.release_lineage import _should_capture_flag


@pytest.mark.parametrize(
    "flag",
    [
        # SUPABASE_RAG_* engine flags (real, present in codebase)
        "SUPABASE_RAG_ENABLED",
        "SUPABASE_RAG_COMPILED_TRUTH_ENABLED",
        "SUPABASE_RAG_COMPILED_TRUTH_SHADOW_ENABLED",
        "SUPABASE_RAG_ENABLE_RERANK",
        "SUPABASE_RAG_FETCH_COUNT",
        # ASSESSMENT_* engine flags
        "ASSESSMENT_USE_SUPABASE",
        "ASSESSMENT_SESSIONS_USE_SUPABASE",
        "ASSESSMENT_ALLOW_DEV_FALLBACK",
        # QUESTION_LIFECYCLE_* authority flag
        "QUESTION_LIFECYCLE_DECISION_AUTHORITY",
        # *_STAGE rollout stage flags
        "SEMANTIC_ROUTER_STAGE",
        "RAG_ROLLOUT_STAGE",
        # *ACTION_LOOP* engine flags
        "ACTION_LOOP_ENABLED",
        "TUTORBOT_ACTION_LOOP_MODE",
    ],
)
def test_engine_level_gray_release_flags_are_captured(flag: str) -> None:
    assert _should_capture_flag(flag) is True


@pytest.mark.parametrize(
    "flag",
    [
        # Legacy contract must keep holding: FF_* and gated DEEPTUTOR_* keys.
        "FF_SOMETHING",
        "DEEPTUTOR_CONTEXT_ORCHESTRATION_ENABLED",
        "DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE",
        "DEEPTUTOR_SOMETHING_STRICT",
    ],
)
def test_legacy_capture_contract_still_holds(flag: str) -> None:
    assert _should_capture_flag(flag) is True


@pytest.mark.parametrize(
    "flag",
    [
        # Pure environment noise must never enter the snapshot, otherwise the
        # ff_snapshot_hash becomes unstable across hosts/CI.
        "PATH",
        "HOME",
        "PWD",
        "LANG",
        "DEEPTUTOR_SERVICE_VERSION",  # lineage input, not a feature flag
    ],
)
def test_environment_noise_is_not_captured(flag: str) -> None:
    assert _should_capture_flag(flag) is False
