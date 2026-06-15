from __future__ import annotations

import importlib.util
import asyncio
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "knowql_nexus_l2_ab",
    REPO / "scripts" / "run_luban_knowql_nexus_l2_learning_ab.py",
)
knowql_nexus_l2_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(knowql_nexus_l2_ab)


def test_build_ws_frame_encodes_arm_intervention_boundaries() -> None:
    scenario = knowql_nexus_l2_ab.DEFAULT_SCENARIOS[0]

    a0 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="A0",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )
    b1 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="B1",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )
    b2 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="B2",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )

    assert "grading_engine_pgo_shadow" not in a0["config"]
    assert "grading_engine_case_rubric_v1" not in b1["config"]
    assert "grading_engine_pgo_shadow" not in b1["config"]
    assert b2["config"]["grading_engine_pgo_shadow"] is True
    assert "knowql_nexus_l2_arm" not in b1["config"]
    assert "knowql_nexus_l2_phase" not in b1["config"]
    assert "nba_intervention_allowed" not in b1["config"]
    assert "nba_intervention_allowed" not in b2["config"]
    assert b2["config"]["client_turn_id"] == "run-l2:l01:B2:initial"


def test_build_ws_frame_encodes_true_entry_three_arm_modes() -> None:
    scenario = knowql_nexus_l2_ab.DEFAULT_SCENARIOS[0]

    a0 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="A0",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )
    b1 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="B1",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )
    b2 = knowql_nexus_l2_ab.build_ws_frame(
        scenario,
        arm="B2",
        run_id="run-l2",
        loop_index=1,
        phase="initial",
        content=scenario.initial_answer,
    )

    assert knowql_nexus_l2_ab.ARM_DEFINITIONS["A0"]["runtime_mode"] == "rag_reference_baseline"
    assert knowql_nexus_l2_ab.ARM_DEFINITIONS["B1"]["runtime_mode"] == "nexus_v1_without_knowql"
    assert knowql_nexus_l2_ab.ARM_DEFINITIONS["B2"]["runtime_mode"] == "nexus_v1_with_knowql"
    assert "grading_engine_pgo_shadow" not in a0["config"]
    assert "grading_engine_case_rubric_v1" not in b1["config"]
    assert "grading_engine_pgo_shadow" not in b1["config"]
    assert "grading_engine_case_rubric_v1" not in b2["config"]
    assert b2["config"]["grading_engine_pgo_shadow"] is True
    assert "billing_context" not in b2["config"]


def test_schedule_balances_learning_arms_without_b3_effect_rows() -> None:
    schedule = knowql_nexus_l2_ab.build_learning_schedule(
        loops=2,
        order_mode="alternating",
        seed=7,
    )

    assert [(item.loop_index, item.arm) for item in schedule] == [
        (1, "A0"),
        (1, "B1"),
        (1, "B2"),
        (2, "B2"),
        (2, "B1"),
        (2, "A0"),
    ]
    assert "B3" not in {item.arm for item in schedule}


def test_summarize_l2_rows_separates_effect_from_safety_and_b3_microbenchmark() -> None:
    rows = [
        _row("A0", "initial", score_ratio=0.20),
        _row("A0", "retest", score_ratio=0.35),
        _row("B1", "initial", score_ratio=0.20),
        _row("B1", "retest", score_ratio=0.40),
        _row("B2", "initial", score_ratio=0.20, pgo=True, g3=True, nba=True),
        _row("B2", "retest", score_ratio=0.70, pgo=True, g3=True, nba=True, nba_applied=True),
    ]
    b3_rows = [
        {"arm": "B3", "ok": True, "duration_ms": 4.0, "payload_bytes": 900, "learning_effect_eligible": False},
        {"arm": "B3", "ok": True, "duration_ms": 5.0, "payload_bytes": 910, "learning_effect_eligible": False},
    ]

    summary = knowql_nexus_l2_ab.summarize_l2_rows(
        rows,
        b3_rows=b3_rows,
        min_loops=1,
        min_b1_delta_lift=0.10,
    )

    assert summary["decision"]["safety_status"] == "L2_SAFETY_GO"
    assert summary["decision"]["effect_status"] == "L2_EFFECT_POSITIVE"
    assert summary["arms"]["B1"]["avg_retest_delta"] == 0.2
    assert summary["arms"]["B2"]["avg_retest_delta"] == 0.5
    assert summary["comparison"]["b2_delta_lift_vs_a0"] == 0.35
    assert summary["comparison"]["b2_delta_lift_vs_b1"] == 0.3
    assert summary["safety"]["b2_nba_intervention_applied_count"] == 1
    assert summary["b3_microbenchmark"]["learning_effect_eligible"] is False
    assert summary["b3_microbenchmark"]["count"] == 2


def test_summarize_l2_rows_reports_ttft_streaming_sealed_and_score_first_metrics() -> None:
    rows = [
        _row("A0", "initial", score_ratio=0.20, ttft_ms=120.0, first_result_ms=900.0, streaming=True),
        _row("A0", "retest", score_ratio=0.20, ttft_ms=130.0, first_result_ms=910.0, streaming=True),
        _row("B1", "initial", score_ratio=0.20, pgo=False, ttft_ms=None, first_result_ms=800.0, streaming=False),
        _row("B1", "retest", score_ratio=0.20, pgo=False, ttft_ms=None, first_result_ms=820.0, streaming=False),
        _row("B2", "initial", score_ratio=0.20, pgo=True, g3=True, nba=True, ttft_ms=80.0, first_result_ms=500.0, streaming=True),
        _row("B2", "retest", score_ratio=0.20, pgo=True, g3=True, nba=True, ttft_ms=90.0, first_result_ms=510.0, streaming=True),
    ]

    summary = knowql_nexus_l2_ab.summarize_l2_rows(rows, b3_rows=[], min_loops=1)

    b2 = summary["arms"]["B2"]
    assert b2["p95_ttft_ms"] == 90.0
    assert b2["p95_result_latency_ms"] == 510.0
    assert b2["streaming_observed_rate"] == 1.0
    assert b2["sealed_block_observed_rate"] == 0.0
    assert b2["sealed_block_not_exercised_count"] == 2
    assert b2["score_first_observed_rate"] == 1.0
    assert summary["comparison"]["score_first_proxy_field"] == "result.metadata.grading_shape.score_first"


def test_summarize_l2_rows_blocks_cross_arm_writes_and_b2_nba_change() -> None:
    rows = [
        _row("A0", "initial", score_ratio=0.20, pgo=True),
        _row("A0", "retest", score_ratio=0.30),
        _row("B1", "initial", score_ratio=0.20, pgo=True, g3=True, nba=True),
        _row("B1", "retest", score_ratio=0.30, pgo=True, g3=True, nba=True),
        _row("B2", "initial", score_ratio=0.20, pgo=True, g3=True, nba=True),
        _row(
            "B2",
            "retest",
            score_ratio=0.30,
            pgo=True,
            g3=True,
            nba=True,
            nba_applied=True,
            canonical_write=True,
        ),
    ]

    summary = knowql_nexus_l2_ab.summarize_l2_rows(rows, b3_rows=[], min_loops=1)

    assert summary["decision"]["safety_status"] == "L2_SAFETY_NO_GO"
    assert "a0_pgo_shadow_present" in summary["decision"]["reasons"]
    assert "canonical_truth_write_detected" in summary["decision"]["reasons"]
    assert "b1_pgo_shadow_present" in summary["decision"]["reasons"]


def test_summarize_l2_rows_accepts_pgo_miss_reduction_as_retest_delta() -> None:
    rows = [
        _row("A0", "initial", score_ratio=0.50),
        _row("A0", "retest", score_ratio=0.50),
        _row("B1", "initial", score_ratio=0.50),
        _row("B1", "retest", score_ratio=0.50),
        _row("B2", "initial", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
        _row("B2", "retest", score_ratio=0.50, pgo=True, g3=True, nba=True, nba_applied=True, pgo_misses=1),
    ]

    summary = knowql_nexus_l2_ab.summarize_l2_rows(
        rows,
        b3_rows=[],
        min_loops=1,
        min_b1_delta_lift=0.05,
        min_b1_pgo_miss_reduction_lift=1.0,
    )

    assert summary["comparison"]["b2_pgo_miss_reduction_lift_vs_b1"] == 1.0
    assert summary["decision"]["effect_status"] == "L2_EFFECT_POSITIVE"


def test_b3_safe_summary_never_persists_teacher_only_payload() -> None:
    payload = {
        "found": True,
        "question_id": "q1",
        "artifact_version": "case_rubric_scored_pgo",
        "scoring_points": [
            {"point_id": "P1", "official_slice": "secret answer text", "criterion": "safe criterion"},
        ],
        "ground": {"source_ref_count": 1},
        "confidence": {"source_validity": 1.0},
    }

    safe = knowql_nexus_l2_ab.safe_knowql_summary(payload)

    assert safe["scoring_point_count"] == 1
    assert "official_slice" not in str(safe)
    assert "secret answer text" not in str(safe)


def test_learning_item_paces_initial_and_retest_turns(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(f"sleep:{seconds}")

    async def fake_run_turn(_frame, item, _scenario, phase, *, nba_applied):
        calls.append(f"{item.arm}:{phase}:{nba_applied}")
        metadata = {}
        if item.arm == "B2" and phase == "initial":
            metadata["pgo_grading_to_brain"] = {
                "next_best_action": {"title": "targeted"},
            }
        return {
            "arm": item.arm,
            "turn_phase": phase,
            "loop_index": item.loop_index,
            "ok": True,
            "duration_ms": 1.0,
            "payload_bytes": 1,
            "metadata": metadata,
        }

    monkeypatch.setattr(knowql_nexus_l2_ab.asyncio, "sleep", fake_sleep)
    rows: list[dict[str, object]] = []

    asyncio.run(knowql_nexus_l2_ab._run_learning_item(
        item=knowql_nexus_l2_ab.RunItem(loop_index=1, arm="B2"),
        order_index=1,
        run_id="run-l2",
        rows=rows,
        run_turn=fake_run_turn,
        inter_turn_delay_seconds=8.0,
    ))

    assert calls == ["B2:initial:False", "sleep:8.0", "B2:retest:True"]
    assert rows[1]["nba_intervention_applied"] is True


def test_row_from_events_captures_true_entry_stream_timings_and_not_exercised_sealed_block(monkeypatch) -> None:
    ticks = iter([100.0, 100.12, 100.3, 100.9])
    monkeypatch.setattr(knowql_nexus_l2_ab.time, "perf_counter", lambda: next(ticks))
    started = 100.0
    events = [
        {"type": "progress", "content": "started"},
        {"type": "content", "content": "先看得分"},
        {
            "type": "result",
            "metadata": {
                "construction_grading_result": {"score_awarded": 1.0, "max_score": 2.0},
                "grading_shape": {
                    "score_first": {
                        "sealed": True,
                        "score": {"score_awarded": 1.0, "max_score": 2.0},
                        "point_verdicts": [{"point_id": "P1", "hit": True}],
                    },
                    "async_explanation_status": "not_exercised",
                },
            },
        },
        {"type": "done"},
    ]

    row = knowql_nexus_l2_ab._row_from_observed_events(
        started=started,
        events=events,
        error="",
        arm="B2",
        loop_index=1,
        turn_phase="initial",
        scenario=knowql_nexus_l2_ab.DEFAULT_SCENARIOS[0],
        nba_intervention_applied=False,
    )

    assert row["ttft_ms"] == 120.0
    assert row["first_result_ms"] == 300.0
    assert row["duration_ms"] == 900.0
    assert row["streaming_observed"] is True
    assert row["content_event_count"] == 1
    assert row["sealed_block_status"] == "not_exercised"
    assert row["score_first_observed"] is True
    assert row["async_explanation_status"] == "not_exercised"


def test_learner_truth_promotion_requires_same_point_retest_verification() -> None:
    rows = [
        _row("B2", "initial", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=1),
        _row("B2", "retest", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=1),
    ]

    blocked = knowql_nexus_l2_ab.build_learner_truth_promotion_preview(rows)

    assert blocked["promotion_allowed"] is False
    assert blocked["canonical_truth_written"] is False
    assert blocked["stable_claim_candidates"] == []
    assert blocked["blocked_reasons"] == ["missing_same_point_retest_improvement"]

    improved_rows = [
        _row("B2", "initial", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
        _row("B2", "retest", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=0),
    ]
    promoted = knowql_nexus_l2_ab.build_learner_truth_promotion_preview(improved_rows)

    assert promoted["promotion_allowed"] is True
    assert promoted["canonical_truth_written"] is False
    assert promoted["stable_claim_candidates"][0]["gate_basis"] == "same_point_retest_verified"


def test_compiler_feedback_loop_materializes_only_actionable_feedback() -> None:
    rows = [
        _row("B2", "initial", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
        _row("B2", "retest", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
        _row("B2", "initial", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
        _row("B2", "retest", score_ratio=0.50, pgo=True, g3=True, nba=True, pgo_misses=2),
    ]
    rows[0]["metadata"]["luban_case_rubric_pgo_shadow"]["low_confidence_point_ids"] = ["P-low"]
    rows[1]["metadata"]["pgo_grading_to_brain"]["teacher_corrections"] = [{"point_id": "P-teacher"}]
    rows[2]["metadata"]["luban_case_rubric_pgo_shadow"]["dispute_point_ids"] = ["P-dispute"]

    feedback = knowql_nexus_l2_ab.build_compiler_feedback_loop(rows)

    assert feedback["compiler_feedback_ready"] is True
    types = {order["feedback_type"] for order in feedback["work_orders"]}
    assert {"low_confidence_point", "teacher_correction", "high_dispute_point", "common_student_miss"} <= types
    assert all(order["promotion_allowed"] is False for order in feedback["work_orders"])


def _row(
    arm: str,
    phase: str,
    *,
    score_ratio: float,
    pgo: bool = False,
    g3: bool = False,
    nba: bool = False,
    nba_applied: bool = False,
    canonical_write: bool = False,
    pgo_misses: int = 1,
    ttft_ms: float | None = 100.0,
    first_result_ms: float | None = 800.0,
    streaming: bool = True,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "construction_grading_result": {
            "score_awarded": score_ratio,
            "max_score": 1.0,
        }
    }
    if pgo:
        verdicts = {"hit": "hit"}
        for index in range(max(0, pgo_misses)):
            verdicts[f"miss_{index + 1}"] = "miss"
        metadata["luban_case_rubric_pgo_shadow"] = {
            "shadow_status": "ok",
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "point_verdicts": verdicts,
            "knowql_query": {"runtime_consumed": True, "fail_open": False},
        }
    if g3:
        metadata["pgo_grading_to_brain"] = {
            "writeback_count": 1,
            "canonical_truth_written": canonical_write,
            "claim_promotion_allowed": False,
            "scoring_point_map_readback": {"items_count": 1},
        }
        if nba:
            metadata["pgo_grading_to_brain"]["next_best_action"] = {
                "title": "先练采分点",
                "prescription_authority": "training_intent",
            }
    return {
        "arm": arm,
        "turn_phase": phase,
        "loop_index": 1,
        "ok": True,
        "duration_ms": 1000.0,
        "payload_bytes": 1000,
        "ttft_ms": ttft_ms,
        "first_result_ms": first_result_ms,
        "streaming_observed": streaming,
        "content_event_count": 1 if streaming else 0,
        "sealed_block_status": "not_exercised",
        "score_first_observed": True,
        "async_explanation_status": "not_exercised",
        "metadata": metadata,
        "nba_intervention_applied": nba_applied,
    }
