from __future__ import annotations

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore


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
