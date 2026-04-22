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
