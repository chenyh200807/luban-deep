from __future__ import annotations

import importlib.util
import asyncio
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "pgo_l1_ab",
    REPO / "scripts" / "run_luban_pgo_l1_live_shadow_ab.py",
)
pgo_l1_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pgo_l1_ab)


def test_build_ws_frame_keeps_pgo_shadow_as_b_arm_only() -> None:
    sample = pgo_l1_ab.DEFAULT_SAMPLES[0]

    arm_a = pgo_l1_ab.build_ws_frame(sample, arm="A", run_id="run-1", pair_index=1)
    arm_b = pgo_l1_ab.build_ws_frame(sample, arm="B", run_id="run-1", pair_index=1)

    assert "grading_engine_pgo_shadow" not in arm_a["config"]
    assert arm_b["config"]["grading_engine_pgo_shadow"] is True
    assert arm_b["config"]["client_turn_id"] == "run-1:p01:B"
    assert arm_b["config"]["followup_question_context"]["question_id"] == sample.question_id
    assert "session_id" not in arm_a
    assert "session_id" not in arm_b


def test_summarize_rows_reports_latency_payload_and_safety_invariants() -> None:
    rows = [
        {
            "arm": "A",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {"construction_grading_result": {"score_awarded": 1}},
        },
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1200.0,
            "payload_bytes": 1300,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"fail_open": False, "runtime_consumed": True},
                },
                "pgo_grading_to_brain": {
                    "canonical_truth_written": False,
                    "claim_promotion_allowed": False,
                },
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows, latency_degradation_threshold=0.25)

    assert summary["arms"]["A"]["success_rate"] == 1.0
    assert summary["arms"]["B"]["p95_latency_ms"] == 1200.0
    assert summary["comparison"]["p95_latency_delta_pct"] == 0.2
    assert summary["comparison"]["payload_bytes_delta"] == 300
    assert summary["safety"]["canonical_truth_write_count"] == 0
    assert summary["safety"]["official_score_write_count"] == 0
    assert summary["safety"]["b_fail_open_count"] == 0
    assert summary["decision"]["status"] == "L1_SHADOW_AB_GO"


def test_summarize_rows_blocks_on_safety_or_latency_regression() -> None:
    rows = [
        {"arm": "A", "ok": True, "duration_ms": 1000.0, "payload_bytes": 1000, "metadata": {}},
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 2000.0,
            "payload_bytes": 1500,
            "metadata": {
                "pgo_grading_to_brain": {"canonical_truth_written": True},
                "luban_case_rubric_pgo_shadow": {"official_score_allowed": True},
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows, latency_degradation_threshold=0.25)

    assert summary["safety"]["canonical_truth_write_count"] == 1
    assert summary["safety"]["official_score_write_count"] == 1
    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "canonical_truth_write_detected" in summary["decision"]["reasons"]
    assert "official_score_write_detected" in summary["decision"]["reasons"]
    assert "p95_latency_regression" in summary["decision"]["reasons"]


def test_summarize_rows_blocks_when_live_ws_has_no_successful_turns() -> None:
    rows = [
        {"arm": "A", "ok": False, "duration_ms": 200.0, "payload_bytes": 200, "metadata": {}},
        {"arm": "B", "ok": False, "duration_ms": 200.0, "payload_bytes": 200, "metadata": {}},
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows)

    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "a_success_rate_zero" in summary["decision"]["reasons"]
    assert "b_success_rate_zero" in summary["decision"]["reasons"]


def test_summarize_rows_does_not_count_killed_shadow_as_effective_pgo() -> None:
    rows = [
        {"arm": "A", "ok": True, "duration_ms": 1000.0, "payload_bytes": 1000, "metadata": {}},
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "killed_by_switch",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                }
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows)

    assert summary["safety"]["b_pgo_shadow_present_count"] == 1
    assert summary["safety"]["b_pgo_shadow_effective_count"] == 0
    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "b_pgo_shadow_not_effective" in summary["decision"]["reasons"]


def test_effective_shadow_requires_ok_status_and_knowql_runtime_consumed() -> None:
    rows = [
        {"arm": "A", "ok": True, "duration_ms": 1000.0, "payload_bytes": 1000, "metadata": {}},
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"runtime_consumed": False},
                }
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows)

    assert summary["safety"]["b_pgo_shadow_effective_count"] == 0
    assert summary["safety"]["b_knowql_runtime_consumed_count"] == 0
    assert "b_pgo_shadow_not_effective" in summary["decision"]["reasons"]
    assert "b_knowql_not_runtime_consumed" in summary["decision"]["reasons"]


def test_safety_summary_scopes_b_metrics_and_blocks_a_shadow_bleed() -> None:
    rows = [
        {
            "arm": "A",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"runtime_consumed": True},
                }
            },
        },
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"runtime_consumed": True},
                }
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows)

    assert summary["safety"]["a_pgo_shadow_present_count"] == 1
    assert summary["safety"]["b_pgo_shadow_present_count"] == 1
    assert summary["safety"]["b_pgo_shadow_effective_count"] == 1
    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "a_pgo_shadow_present" in summary["decision"]["reasons"]


def test_write_detection_blocks_all_write_signals() -> None:
    rows = [
        {"arm": "A", "ok": True, "duration_ms": 1000.0, "payload_bytes": 1000, "metadata": {}},
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": True,
                    "writeback_performed": True,
                    "knowql_query": {"runtime_consumed": True},
                },
                "pgo_grading_to_brain": {
                    "claim_promotion_allowed": True,
                    "canonical_truth_written": False,
                    "db_write_count": 1,
                    "remote_write_count": 0,
                    "production_write_count": 0,
                },
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows)

    assert summary["safety"]["canonical_truth_write_count"] == 1
    assert summary["safety"]["unsafe_write_signal_count"] == 4
    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "canonical_truth_write_detected" in summary["decision"]["reasons"]
    assert "unsafe_write_signal_detected" in summary["decision"]["reasons"]


def test_activation_probe_requires_effective_shadow_and_knowql_consumption() -> None:
    blocked = pgo_l1_ab.summarize_activation_probe([
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "killed_by_switch",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                }
            },
        }
    ])

    assert blocked["decision"]["status"] == "L1_ACTIVATION_BLOCKED"
    assert "b_pgo_shadow_not_effective" in blocked["decision"]["reasons"]

    ready = pgo_l1_ab.summarize_activation_probe([
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"runtime_consumed": True, "found": True},
                }
            },
        }
    ])

    assert ready["decision"]["status"] == "L1_ACTIVATION_READY"
    assert ready["safety"]["b_pgo_shadow_effective_count"] == 1
    assert ready["safety"]["b_knowql_runtime_consumed_count"] == 1


def test_summarize_rows_requires_requested_pair_count() -> None:
    rows = [
        {"arm": "A", "ok": True, "duration_ms": 1000.0, "payload_bytes": 1000, "metadata": {}},
        {
            "arm": "B",
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "ok",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                    "knowql_query": {"runtime_consumed": True},
                }
            },
        },
    ]

    summary = pgo_l1_ab.summarize_ab_rows(rows, min_pairs=30)

    assert summary["comparison"]["completed_pairs"] == 1
    assert summary["decision"]["status"] == "L1_SHADOW_AB_NO_GO"
    assert "insufficient_pair_count" in summary["decision"]["reasons"]


def test_build_run_schedule_alternates_ab_and_ba_order() -> None:
    schedule = pgo_l1_ab.build_run_schedule(pairs=3, order_mode="alternating", seed=7)

    assert [(item.pair_index, item.arm) for item in schedule] == [
        (1, "A"),
        (1, "B"),
        (2, "B"),
        (2, "A"),
        (3, "A"),
        (3, "B"),
    ]


def test_run_live_shadow_ab_uses_schedule_and_min_pair_gate(tmp_path, monkeypatch) -> None:
    calls = []

    async def fake_run_one_ws_turn(**kwargs):
        calls.append((kwargs["order_index"], kwargs["pair_index"], kwargs["arm"]))
        metadata = {}
        if kwargs["arm"] == "B":
            metadata["luban_case_rubric_pgo_shadow"] = {
                "shadow_status": "ok",
                "official_score_allowed": False,
                "canonical_write_allowed": False,
                "knowql_query": {"runtime_consumed": True, "fail_open": False},
            }
        return {
            "pair_index": kwargs["pair_index"],
            "order_index": kwargs["order_index"],
            "arm": kwargs["arm"],
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": metadata,
        }

    monkeypatch.setattr(pgo_l1_ab, "_run_one_ws_turn", fake_run_one_ws_turn)

    result = asyncio.run(pgo_l1_ab.run_live_shadow_ab(
        api_base_url="https://example.test",
        token="token",
        pairs=2,
        timeout_seconds=1.0,
        out_dir=tmp_path,
        latency_degradation_threshold=0.25,
        max_b_fail_open_rate=0.05,
        min_b_shadow_rate=1.0,
        min_pairs=2,
        order_mode="alternating",
        seed=17,
        connection_mode="per-turn",
        inter_turn_delay_seconds=0.0,
    ))

    assert calls == [(1, 1, "A"), (2, 1, "B"), (3, 2, "B"), (4, 2, "A")]
    assert result["summary"]["comparison"]["completed_pairs"] == 2
    assert result["summary"]["decision"]["status"] == "L1_SHADOW_AB_GO"
    assert result["manifest"]["order_mode"] == "alternating"
    assert result["manifest"]["sample_ids"] == ["pgo_known_xw2015_e0"]


def test_run_live_shadow_ab_single_connection_reuses_ws(tmp_path, monkeypatch) -> None:
    calls = []
    connections = []

    class _FakeConnection:
        async def __aenter__(self):
            connections.append("enter")
            return self

        async def __aexit__(self, *_args):
            connections.append("exit")

    async def fake_run_one_ws_turn_on_connection(**kwargs):
        calls.append((kwargs["websocket"].__class__.__name__, kwargs["order_index"], kwargs["pair_index"], kwargs["arm"]))
        metadata = {}
        if kwargs["arm"] == "B":
            metadata["luban_case_rubric_pgo_shadow"] = {
                "shadow_status": "ok",
                "official_score_allowed": False,
                "canonical_write_allowed": False,
                "knowql_query": {"runtime_consumed": True, "fail_open": False},
            }
        return {
            "pair_index": kwargs["pair_index"],
            "order_index": kwargs["order_index"],
            "arm": kwargs["arm"],
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": metadata,
        }

    monkeypatch.setattr(pgo_l1_ab, "_connect_ws", lambda *_args, **_kwargs: _FakeConnection())
    monkeypatch.setattr(
        pgo_l1_ab,
        "_run_one_ws_turn_on_connection",
        fake_run_one_ws_turn_on_connection,
        raising=False,
    )

    result = asyncio.run(pgo_l1_ab.run_live_shadow_ab(
        api_base_url="https://example.test",
        token="token",
        pairs=2,
        timeout_seconds=1.0,
        out_dir=tmp_path,
        latency_degradation_threshold=0.25,
        max_b_fail_open_rate=0.05,
        min_b_shadow_rate=1.0,
        min_pairs=2,
        order_mode="alternating",
        seed=17,
        connection_mode="single",
        inter_turn_delay_seconds=0.0,
    ))

    assert connections == ["enter", "exit"]
    assert calls == [
        ("_FakeConnection", 1, 1, "A"),
        ("_FakeConnection", 2, 1, "B"),
        ("_FakeConnection", 3, 2, "B"),
        ("_FakeConnection", 4, 2, "A"),
    ]
    assert result["summary"]["decision"]["status"] == "L1_SHADOW_AB_GO"
    assert result["manifest"]["connection_mode"] == "single"


def test_run_activation_probe_writes_blocked_summary(tmp_path, monkeypatch) -> None:
    async def fake_run_one_ws_turn(**kwargs):
        return {
            "pair_index": kwargs["pair_index"],
            "arm": kwargs["arm"],
            "ok": True,
            "duration_ms": 1000.0,
            "payload_bytes": 1000,
            "metadata": {
                "luban_case_rubric_pgo_shadow": {
                    "shadow_status": "killed_by_switch",
                    "official_score_allowed": False,
                    "canonical_write_allowed": False,
                }
            },
        }

    monkeypatch.setattr(pgo_l1_ab, "_run_one_ws_turn", fake_run_one_ws_turn)

    result = asyncio.run(pgo_l1_ab.run_activation_probe(
        api_base_url="https://example.test",
        token="token",
        timeout_seconds=1.0,
        out_dir=tmp_path,
    ))

    assert result["summary"]["decision"]["status"] == "L1_ACTIVATION_BLOCKED"
    assert (tmp_path / "activation_probe.json").exists()


def test_markdown_report_contains_l1_audit_fields(tmp_path) -> None:
    manifest = {
        "api_base_url": "https://example.test",
        "pairs": 30,
        "min_pairs": 30,
        "order_mode": "alternating",
        "seed": 20260615,
        "sample_ids": ["pgo_known_xw2015_e0"],
        "activation_probe_status": "L1_ACTIVATION_READY",
        "exit_code_intent": {"go": 0, "no_go": 1, "auth_blocked": 2, "activation_blocked": 3},
    }
    summary = {
        "decision": {"status": "L1_SHADOW_AB_GO", "reasons": []},
        "comparison": {
            "p95_latency_delta_pct": 0.01,
            "payload_bytes_delta": 2,
            "completed_pairs": 30,
            "b_fail_open_rate": 0.0,
            "b_pgo_shadow_effective_rate": 1.0,
            "b_knowql_runtime_consumed_rate": 1.0,
        },
        "safety": {
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "unsafe_write_signal_count": 0,
            "a_pgo_shadow_present_count": 0,
            "b_fail_open_count": 0,
            "b_pgo_shadow_present_count": 30,
            "b_pgo_shadow_effective_count": 30,
            "b_knowql_runtime_consumed_count": 30,
            "pgo_g3_preview_readback_count": 0,
        },
    }

    path = tmp_path / "finding.md"
    pgo_l1_ab._write_markdown(path, manifest=manifest, summary=summary)
    text = path.read_text(encoding="utf-8")

    assert "activation probe status" in text
    assert "completed pairs" in text
    assert "B KnowQL runtime consumed count" in text
    assert "exit code intent" in text
