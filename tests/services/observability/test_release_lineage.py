from __future__ import annotations

from deeptutor.services.observability.release_lineage import (
    get_release_lineage_snapshot,
    reset_release_lineage_cache,
)


def test_release_lineage_uses_env_inputs_and_builds_stable_release_id(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_SERVICE_VERSION", "1.2.3")
    monkeypatch.setenv("DEEPTUTOR_GIT_SHA", "abc123def456")
    monkeypatch.setenv("DEEPTUTOR_ENV", "prod")
    monkeypatch.setenv("DEEPTUTOR_PROMPT_VERSION", "prompt-v7")
    monkeypatch.setenv("DEEPTUTOR_CONTEXT_ORCHESTRATION_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE", "false")
    reset_release_lineage_cache()

    snapshot = get_release_lineage_snapshot()

    assert snapshot["service_version"] == "1.2.3"
    assert snapshot["git_sha"] == "abc123def456"
    assert snapshot["deployment_environment"] == "prod"
    assert snapshot["prompt_version"] == "prompt-v7"
    assert snapshot["release_id"] == "1.2.3+abc123def456+prod"
    assert snapshot["ff_snapshot_hash"] != "none"


def test_release_lineage_respects_explicit_release_id_override(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_RELEASE_ID", "release-demo-2026-04-19")
    monkeypatch.setenv("DEEPTUTOR_GIT_SHA", "zzz999")
    monkeypatch.setenv("DEEPTUTOR_ENV", "staging")
    reset_release_lineage_cache()

    snapshot = get_release_lineage_snapshot()

    assert snapshot["release_id"] == "release-demo-2026-04-19"
