from __future__ import annotations

from deeptutor.services.observability import change_impact
from deeptutor.services.observability.change_impact import build_change_impact_run
from deeptutor.services.observability.change_impact import collect_git_changed_files
from deeptutor.services.observability.change_impact import parse_git_status_changed_files


def test_parse_git_status_changed_files_preserves_tracked_paths() -> None:
    assert parse_git_status_changed_files(
        " M deeptutor/services/session/turn_runtime.py\n"
        "?? scripts/run_change_impact.py\n"
        "R  old/path.py -> deeptutor/services/rag/pipelines/supabase.py\n"
    ) == [
        "deeptutor/services/rag/pipelines/supabase.py",
        "deeptutor/services/session/turn_runtime.py",
        "scripts/run_change_impact.py",
    ]


def test_build_change_impact_run_maps_changed_files_to_domains_and_gates() -> None:
    payload = build_change_impact_run(
        changed_files=[
            "deeptutor/services/session/turn_runtime.py",
            "deeptutor/services/rag/pipelines/supabase.py",
            "web/lib/unified-ws.ts",
        ],
        observer_payload={
            "run_id": "observer-1",
            "release": {"release_id": "rel-1", "git_sha": "abc123"},
            "data_coverage": {"coverage_ratio": 0.7},
            "blind_spots": [{"type": "missing_surface_coverage", "severity": "medium"}],
            "turn_events": {"event_count": 10, "error_ratio": 0.1},
        },
        om_payload={"run_id": "om-1", "health_summary": {"ready": True}},
        arr_payload={
            "run_id": "arr-1",
            "summary": {"pass_rate": 0.8},
            "baseline_diff": {"regressions": [{"case_key": "ld-001"}], "new_failures": []},
        },
        aae_payload={"run_id": "aae-1", "scorecard": {"continuity_score": {"value": 0.72}}},
    )

    domains = {item["domain"] for item in payload["changed_domains"]}
    gates = {item["gate"] for item in payload["required_gates"]}

    assert {"turn", "rag", "surface"}.issubset(domains)
    assert {"contract_guard", "unified_ws_smoke", "arr_lite", "aae_snapshot", "observer_snapshot"}.issubset(gates)
    assert payload["risk_level"] == "high"
    assert payload["first_failing_signal"]["type"] == "arr_regressions"
    assert payload["score_components"]
    assert any(item["source"] == "domain" and item["name"] == "high_risk_domain" for item in payload["score_components"])
    assert any(item["source"] == "signal" and item["name"] == "arr_regressions" for item in payload["score_components"])
    assert payload["blocking_recommendation"] == "hold"
    assert any("scripts/run_arr_lite.py" in item for item in payload["next_commands"])


def test_build_change_impact_run_marks_no_changes_as_blind_spot() -> None:
    payload = build_change_impact_run(changed_files=[], observer_payload=None)

    assert payload["risk_level"] == "unknown"
    assert any(item["type"] == "missing_changed_files" for item in payload["blind_spots"])
    assert any(item["gate"] == "observer_snapshot" for item in payload["required_gates"])


def test_collect_git_changed_files_defaults_to_previous_commit(monkeypatch) -> None:
    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN202
        calls.append(list(args))
        return _Result()

    monkeypatch.setattr("deeptutor.services.observability.change_impact.subprocess.run", fake_run)

    assert collect_git_changed_files() == []
    assert change_impact.DEFAULT_CHANGE_IMPACT_BASE_REF == "HEAD~1"
    assert calls[0] == ["git", "diff", "--name-only", "HEAD~1"]


def test_build_change_impact_run_maps_bi_backend_to_bi_domain_and_gates() -> None:
    payload = build_change_impact_run(
        changed_files=[
            "deeptutor/services/bi_service.py",
            "deeptutor/services/member_console/service.py",
            "web/lib/bi-api.ts",
        ],
        observer_payload={
            "run_id": "observer-1",
            "release": {"release_id": "rel-1", "git_sha": "abc123"},
            "turn_events": {"event_count": 1, "error_ratio": 0.0},
            "blind_spots": [],
        },
    )

    domains = {item["domain"]: item for item in payload["changed_domains"]}
    gates = {item["gate"] for item in payload["required_gates"]}

    assert "bi" in domains
    assert domains["bi"]["risk"] == "medium"
    assert "bi_service_tests" in gates
    assert "bi_web_tests" in gates
    assert "other" not in domains
