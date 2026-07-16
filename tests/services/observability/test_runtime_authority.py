from __future__ import annotations

from deeptutor.services.observability.runtime_authority import evaluate_runtime_authority
from deeptutor.services.observability.runtime_authority import release_identity_matches


def _release(**overrides):
    payload = {
        "release_id": "rel-1",
        "git_sha": "abc",
        "deployment_environment": "production",
        "prompt_version": "prompt-1",
        "ff_snapshot_hash": "ff-1",
        "deploy_manifest_hash": "manifest-1",
        "git_dirty": "false",
    }
    payload.update(overrides)
    return payload


def _live_metrics(release):
    return {
        "release": release,
        "observability_metrics_provenance": {
            "source": "live_metrics_endpoint",
            "fallback_used": False,
            "status_code": 200,
        },
    }


def test_runtime_authority_requires_complete_clean_live_identity() -> None:
    expected = _release()
    assert evaluate_runtime_authority(
        expected_release=expected, metrics_snapshot=_live_metrics(_release())
    )["status"] == "PASS"

    for field, value in (
        ("git_sha", "other"),
        ("deployment_environment", "staging"),
        ("ff_snapshot_hash", "other-ff"),
        ("deploy_manifest_hash", "other-manifest"),
        ("git_dirty", "true"),
    ):
        result = evaluate_runtime_authority(
            expected_release=expected,
            metrics_snapshot=_live_metrics(_release(**{field: value})),
        )
        assert result["status"] == "BLOCKED", field


def test_runtime_authority_never_promotes_artifact_or_error() -> None:
    expected = _release()
    artifact = _live_metrics(_release())
    artifact["observability_metrics_provenance"]["source"] = "metrics_json"
    assert evaluate_runtime_authority(expected_release=expected, metrics_snapshot=artifact)["status"] == "ARTIFACT_ONLY"
    assert evaluate_runtime_authority(
        expected_release=expected,
        metrics_snapshot=None,
        metrics_error={"source": "live_metrics_endpoint", "fallback_used": False, "error": "ConnectError"},
    )["status"] == "BLOCKED"


def test_release_identity_rejects_same_sha_with_foreign_lineage() -> None:
    assert not release_identity_matches(_release(), _release(ff_snapshot_hash="foreign"))
    assert not release_identity_matches(_release(), _release(deploy_manifest_hash="foreign"))
    assert not release_identity_matches(_release(), _release(git_dirty="true"))
    incomplete = _release()
    incomplete.pop("deploy_manifest_hash")
    assert not release_identity_matches(incomplete, _release())
