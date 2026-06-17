from __future__ import annotations

import subprocess

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
    monkeypatch.setenv("DEEPTUTOR_GIT_DIRTY", "false")
    monkeypatch.setenv("DEEPTUTOR_DEPLOY_MANIFEST_HASH", "manifest123")
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
    assert snapshot["git_dirty"] == "false"
    assert snapshot["deploy_manifest_hash"] == "manifest123"


def test_release_lineage_respects_explicit_release_id_override(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_RELEASE_ID", "release-demo-2026-04-19")
    monkeypatch.setenv("DEEPTUTOR_GIT_SHA", "zzz999")
    monkeypatch.setenv("DEEPTUTOR_ENV", "staging")
    reset_release_lineage_cache()

    snapshot = get_release_lineage_snapshot()

    assert snapshot["release_id"] == "release-demo-2026-04-19"


def test_release_lineage_exposes_dirty_tree_marker(monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_GIT_DIRTY", "true")
    monkeypatch.setenv("DEEPTUTOR_DEPLOY_MANIFEST_HASH", "dirtyhash")
    reset_release_lineage_cache()

    snapshot = get_release_lineage_snapshot()

    assert snapshot["git_dirty"] == "true"
    assert snapshot["deploy_manifest_hash"] == "dirtyhash"


def test_release_lineage_derives_local_control_plane_fields_when_env_missing(monkeypatch) -> None:
    for name in (
        "DEEPTUTOR_RELEASE_ID",
        "DEEPTUTOR_GIT_SHA",
        "GIT_SHA",
        "COMMIT_SHA",
        "DEEPTUTOR_ENV",
        "APP_ENV",
        "ENVIRONMENT",
        "ENV",
        "DEEPTUTOR_PROMPT_VERSION",
        "PROMPT_VERSION",
        "NEXT_PUBLIC_PROMPT_VERSION",
        "DEEPTUTOR_FF_SNAPSHOT_HASH",
        "FF_SNAPSHOT_HASH",
        "DEEPTUTOR_GIT_DIRTY",
        "GIT_DIRTY",
        "DEEPTUTOR_DEPLOY_MANIFEST_HASH",
        "DEPLOY_MANIFEST_HASH",
    ):
        monkeypatch.delenv(name, raising=False)

    def fake_run(command, **_kwargs):
        if command[-3:] == ["rev-parse", "--short=12", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="abc123def456\n", stderr="")
        if command[-3:] == ["rev-parse", "--short=12", "HEAD^{tree}"]:
            return subprocess.CompletedProcess(command, 0, stdout="tree12345678\n", stderr="")
        if command[-3:] == ["status", "--porcelain", "--untracked-files=normal"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected git command: {command}")

    monkeypatch.setattr("deeptutor.services.observability.release_lineage.subprocess.run", fake_run)
    reset_release_lineage_cache()

    snapshot = get_release_lineage_snapshot()

    assert snapshot["git_sha"] == "abc123def456"
    assert snapshot["deployment_environment"] == "local"
    assert snapshot["prompt_version"] == "git-abc123def456"
    assert snapshot["ff_snapshot_hash"] != "none"
    assert snapshot["git_dirty"] == "false"
    assert snapshot["deploy_manifest_hash"] == "local-tree12345678"
    assert snapshot["release_id"] == "1.0.0+abc123def456+local"
