from __future__ import annotations

import pytest

import deeptutor.services.observability.control_plane_freshness as freshness
from deeptutor.services.observability.control_plane_freshness import (
    FRESHNESS_SECONDS,
    record_is_fresh,
    select_fresh_payload_for_release,
)
from deeptutor.services.observability.readiness_matrix import (
    build_current_release_readiness_matrix_payload,
)


class _Store:
    def __init__(self, records):
        self.records = records

    def list_runs(self, _kind, limit=100):
        return self.records[:limit]

    def latest_run(self, _kind, fallback=False):
        del fallback
        return self.records[0] if self.records else None


def _release(**overrides):
    release = {
        "release_id": "rel-1",
        "git_sha": "abc",
        "deployment_environment": "production",
        "prompt_version": "prompt-1",
        "ff_snapshot_hash": "ff-1",
        "deploy_manifest_hash": "manifest-1",
        "git_dirty": "false",
    }
    release.update(overrides)
    return release


def _record(*, recorded_at, release=None):
    return {
        "recorded_at": recorded_at,
        "payload": {"run_id": "run-1", "release": release or _release()},
    }


def test_selector_accepts_only_same_lineage_with_fresh_wrapper_time() -> None:
    now = 1_000_000.0
    limit = FRESHNESS_SECONDS["benchmark_runs"]
    assert select_fresh_payload_for_release(
        store=_Store([_record(recorded_at=now - limit + 1)]),
        kind="benchmark_runs",
        release=_release(),
        now=now,
    )["run_id"] == "run-1"

    for record in (
        _record(recorded_at=now - limit - 1),
        _record(recorded_at=None),
        _record(recorded_at=now + 1),
        _record(recorded_at=now - 1, release=_release(service_version="2.0.0")),
        _record(recorded_at=now - 1, release=_release(ff_snapshot_hash="foreign")),
    ):
        assert select_fresh_payload_for_release(
            store=_Store([record]),
            kind="benchmark_runs",
            release=_release(),
            now=now,
        ) is None


def test_freshness_threshold_and_unknown_kind_are_fail_closed() -> None:
    now = 1_000_000.0
    limit = FRESHNESS_SECONDS["readiness_checks"]
    assert record_is_fresh(
        {"recorded_at": now - limit},
        kind="readiness_checks",
        now=now,
    )
    assert not record_is_fresh(
        {"recorded_at": now - limit - 0.001},
        kind="readiness_checks",
        now=now,
    )
    assert not record_is_fresh(
        {"recorded_at": now - 1},
        kind="unknown_kind",
        now=now,
    )
    assert record_is_fresh(
        {"recorded_at": 1},
        kind="incident_ledger",
        now=now,
    )


def test_readiness_anchor_ignores_stale_newest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000_000.0
    stale_release = _release(release_id="stale", git_sha="old")
    fresh_release = _release(release_id="fresh", git_sha="new")
    stale = {
        "run_id": "stale-check",
        "recorded_at": now - FRESHNESS_SECONDS["readiness_checks"] - 1,
        "payload": {
            "run_id": "stale-check",
            "check_id": "contract_guard",
            "status": "PASS",
            "release": stale_release,
        },
    }
    fresh = {
        "run_id": "fresh-check",
        "recorded_at": now,
        "payload": {
            "run_id": "fresh-check",
            "check_id": "contract_guard",
            "status": "PASS",
            "release": fresh_release,
        },
    }
    store = _Store([stale, fresh])

    monkeypatch.setattr(freshness.time, "time", lambda: now)
    payload = build_current_release_readiness_matrix_payload(store=store)

    assert payload["release"]["release_id"] == "fresh"
    assert [row["run_id"] for row in payload["rows"]] == ["fresh-check"]
