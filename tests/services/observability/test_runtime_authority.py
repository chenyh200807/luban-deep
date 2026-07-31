from __future__ import annotations

from deeptutor.services.observability.runtime_authority import (
    evaluate_runtime_authority,
    release_identity_matches,
)


def _release(**overrides):
    payload = {
        "release_id": "rel-1",
        "service_version": "1.0.0",
        "git_sha": "abc",
        "deployment_environment": "production",
        "prompt_version": "prompt-1",
        "ff_snapshot_hash": "ff-1",
        "deploy_manifest_hash": "a" * 64,
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
            "url": "https://runtime.example/metrics",
        },
    }


def _evaluate(**kwargs):
    return evaluate_runtime_authority(
        expected_metrics_url="https://runtime.example/metrics",
        governed_metrics_urls=("https://runtime.example/metrics",),
        **kwargs,
    )


def test_runtime_authority_requires_complete_clean_live_identity() -> None:
    expected = _release()
    assert _evaluate(
        expected_release=expected, metrics_snapshot=_live_metrics(_release())
    )["status"] == "PASS"

    for field, value in (
        ("release_id", "rel-2"),
        ("service_version", "2.0.0"),
        ("git_sha", "other"),
        ("deployment_environment", "staging"),
        ("prompt_version", "prompt-2"),
        ("ff_snapshot_hash", "other-ff"),
        ("deploy_manifest_hash", "b" * 64),
        ("git_dirty", "true"),
    ):
        result = _evaluate(
            expected_release=expected,
            metrics_snapshot=_live_metrics(_release(**{field: value})),
        )
        assert result["status"] == "BLOCKED", field


def test_runtime_authority_never_promotes_artifact_or_error() -> None:
    expected = _release()
    artifact = _live_metrics(_release())
    artifact["observability_metrics_provenance"]["source"] = "metrics_json"
    assert _evaluate(expected_release=expected, metrics_snapshot=artifact)["status"] == "ARTIFACT_ONLY"
    assert _evaluate(
        expected_release=expected,
        metrics_snapshot=None,
        metrics_error={"source": "live_metrics_endpoint", "fallback_used": False, "error": "ConnectError"},
    )["status"] == "BLOCKED"


def test_runtime_authority_requires_canonical_live_metrics_provenance() -> None:
    expected = _release()
    for overrides in (
        {"status_code": None},
        {"url": ""},
        {"url": "https://other.example/metrics"},
    ):
        metrics = _live_metrics(_release())
        metrics["observability_metrics_provenance"].update(overrides)
        result = _evaluate(
            expected_release=expected,
            metrics_snapshot=metrics,
        )
        assert result["status"] == "ARTIFACT_ONLY"


def test_runtime_authority_rejects_unregistered_loopback_target() -> None:
    metrics = _live_metrics(_release())
    metrics["observability_metrics_provenance"]["url"] = "http://127.0.0.1:8001/metrics"
    result = evaluate_runtime_authority(
        expected_release=_release(),
        metrics_snapshot=metrics,
        expected_metrics_url="http://127.0.0.1:8001/metrics",
        governed_metrics_urls=("https://test2.example/metrics",),
    )
    assert result["status"] == "ARTIFACT_ONLY"
    assert result["governed_target"] is False


def test_runtime_authority_rejects_ungoverned_local_demo() -> None:
    local_release = _release(
        deployment_environment="local",
        deploy_manifest_hash="local-manifest",
    )
    result = _evaluate(
        expected_release=local_release,
        metrics_snapshot=_live_metrics(local_release),
    )
    assert result["status"] == "BLOCKED"
    assert result["governed_runtime"] is False

    production_with_local_manifest = _release(deploy_manifest_hash="local-demo")
    result = _evaluate(
        expected_release=production_with_local_manifest,
        metrics_snapshot=_live_metrics(production_with_local_manifest),
    )
    assert result["status"] == "BLOCKED"
    assert result["governed_runtime"] is False

    arbitrary_label = _release(deployment_environment="prouction")
    result = _evaluate(
        expected_release=arbitrary_label,
        metrics_snapshot=_live_metrics(arbitrary_label),
    )
    assert result["status"] == "BLOCKED"
    assert result["governed_runtime"] is False


def test_release_identity_rejects_same_sha_with_foreign_lineage() -> None:
    assert not release_identity_matches(_release(), _release(ff_snapshot_hash="foreign"))
    assert not release_identity_matches(_release(), _release(deploy_manifest_hash="foreign"))
    assert not release_identity_matches(_release(), _release(git_dirty="true"))
    incomplete = _release()
    incomplete.pop("deploy_manifest_hash")
    assert not release_identity_matches(incomplete, _release())
