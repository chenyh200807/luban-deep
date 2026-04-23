from __future__ import annotations

import json

import pytest

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore
from deeptutor.services.observability.control_plane_store import load_payload_json


def test_control_plane_store_writes_and_reads_latest_and_history(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)

    paths = store.write_run(
        kind="arr_runs",
        run_id="arr-lite-1",
        release_id="rel-1",
        payload={"summary": {"pass_rate": 1.0}},
    )

    assert paths["json_path"].endswith("arr-lite-1.json")
    latest = store.latest_run("arr_runs")
    assert latest is not None
    assert latest["run_id"] == "arr-lite-1"
    assert latest["payload"]["summary"]["pass_rate"] == 1.0
    assert store.latest_payload("arr_runs") == {"summary": {"pass_rate": 1.0}}

    history = store.list_runs("arr_runs")
    assert len(history) == 1
    assert history[0]["release_id"] == "rel-1"


def test_control_plane_store_accepts_change_impact_runs(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)

    store.write_run(
        kind="change_impact_runs",
        run_id="change-impact-1",
        release_id="rel-1",
        payload={"risk_level": "high", "changed_domains": [{"domain": "turn"}]},
    )

    assert store.latest_payload("change_impact_runs") == {
        "risk_level": "high",
        "changed_domains": [{"domain": "turn"}],
    }


def test_control_plane_store_rejects_unknown_kind(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)

    try:
        store.write_run(kind="unknown_kind", run_id="x", release_id="r", payload={})
    except ValueError as exc:
        assert "Unsupported control plane kind" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_load_payload_json_unwraps_control_plane_record(tmp_path) -> None:
    payload = {"run_id": "arr-lite-1", "summary": {"pass_rate": 1.0}}
    wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-lite-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": payload,
    }
    target = tmp_path / "arr-control-plane.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    assert load_payload_json(target, expected_kind="arr_runs") == payload


def test_load_payload_json_rejects_mismatched_control_plane_kind(tmp_path) -> None:
    wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-lite-1",
        "release_id": "rel-1",
        "recorded_at": 123,
        "payload": {"run_id": "arr-lite-1"},
    }
    target = tmp_path / "wrong-kind.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="expected 'om_runs'"):
        load_payload_json(target, expected_kind="om_runs")


def test_load_payload_json_rejects_wrapper_missing_recorded_at(tmp_path) -> None:
    wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-lite-1",
        "release_id": "rel-1",
        "payload": {"run_id": "arr-lite-1"},
    }
    target = tmp_path / "missing-recorded-at.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing 'recorded_at'"):
        load_payload_json(target, expected_kind="arr_runs")


def test_load_payload_json_rejects_wrapper_missing_release_id(tmp_path) -> None:
    wrapper = {
        "kind": "arr_runs",
        "run_id": "arr-lite-1",
        "recorded_at": 123,
        "payload": {"run_id": "arr-lite-1"},
    }
    target = tmp_path / "missing-release-id.json"
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing 'release_id'"):
        load_payload_json(target, expected_kind="arr_runs")


def test_control_plane_store_latest_payload_rejects_malformed_wrapper(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)
    latest_path = tmp_path / "arr_runs" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "kind": "arr_runs",
                "run_id": "arr-lite-1",
                "release_id": "rel-1",
                "recorded_at": 123,
                "payload": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain dict payload"):
        store.latest_payload("arr_runs")


def test_control_plane_store_latest_payload_skips_malformed_latest_json(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)
    kind_dir = tmp_path / "oa_runs"
    kind_dir.mkdir(parents=True, exist_ok=True)
    (kind_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "oa_runs",
                "run_id": "oa-latest",
                "recorded_at": 456,
                "payload": {"run_id": "oa-latest"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (kind_dir / "oa-older.json").write_text(
        json.dumps(
            {
                "kind": "oa_runs",
                "run_id": "oa-older",
                "release_id": "rel-1",
                "recorded_at": 123,
                "payload": {"run_id": "oa-older", "blockers": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert store.latest_payload("oa_runs") == {"run_id": "oa-older", "blockers": []}


def test_control_plane_store_latest_run_uses_same_fallback_as_latest_payload(tmp_path) -> None:
    store = ObservabilityControlPlaneStore(base_dir=tmp_path)
    kind_dir = tmp_path / "observer_snapshots"
    kind_dir.mkdir(parents=True, exist_ok=True)
    (kind_dir / "latest.json").write_text(
        json.dumps(
            {
                "kind": "observer_snapshots",
                "run_id": "observer-bad",
                "recorded_at": 456,
                "payload": {"run_id": "observer-bad"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (kind_dir / "observer-good.json").write_text(
        json.dumps(
            {
                "kind": "observer_snapshots",
                "run_id": "observer-good",
                "release_id": "rel-1",
                "recorded_at": 123,
                "payload": {"run_id": "observer-good", "blind_spots": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    latest_run = store.latest_run("observer_snapshots")
    assert latest_run is not None
    assert latest_run["run_id"] == "observer-good"
    assert store.latest_payload("observer_snapshots") == {"run_id": "observer-good", "blind_spots": []}
