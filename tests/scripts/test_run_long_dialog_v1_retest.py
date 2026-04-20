from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_long_dialog_v1_retest.py"
)
SPEC = importlib.util.spec_from_file_location("run_long_dialog_v1_retest", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.asyncio
async def test_run_case_records_ttft_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_turn(*_args, session_id=None, query: str, teaching_mode: str, **_kwargs):
        if "第一问" in query:
            return session_id or "session-1", "答复一", 12_000.0, 55_000.0, ["content", "result"]
        return session_id or "session-1", "答复二", 8_000.0, 30_000.0, ["content", "result"]

    monkeypatch.setattr(MODULE, "_run_single_turn", _fake_run_single_turn)

    case = {
        "case_id": "LD_TEST",
        "title": "TTFT 统计",
        "source_session_id": "src-1",
        "turns": [
            {"turn": 1, "user_query": "第一问"},
            {"turn": 2, "user_query": "第二问"},
        ],
    }

    result = await MODULE._run_case(
        case,
        teaching_mode="smart",
        per_turn_timeout_s=5.0,
        turn_mode="full",
    )

    assert result["turns"][0]["ttft_ms"] == 12_000.0
    assert result["turns"][1]["ttft_ms"] == 8_000.0
    assert result["summary"]["avg_ttft_ms"] == 10_000.0
    assert result["summary"]["p50_ttft_ms"] == 10_000.0
    assert result["summary"]["p90_ttft_ms"] == 11_600.0


def test_render_markdown_includes_ttft_overview() -> None:
    results = [
        {
            "case_id": "LD_TEST",
            "title": "TTFT 统计",
            "source_session_id": "src-1",
            "summary": {
                "turns": 2,
                "hard_errors": 0,
                "followup_object_mismatch_count": 0,
                "question_count_mismatch_count": 0,
                "anchor_miss_count": 0,
                "context_reset_count": 0,
                "compare_table_miss_count": 0,
                "stale_replay_count": 0,
                "slow_turns": 1,
                "avg_latency_ms": 42_500.0,
                "avg_ttft_ms": 10_000.0,
                "p50_ttft_ms": 10_000.0,
                "p90_ttft_ms": 11_600.0,
                "semantic_score": 95,
                "satisfaction_score": 90,
                "aborted": False,
                "abort_reason": "",
            },
            "turns": [
                {
                    "turn": 1,
                    "query": "第一问",
                    "response": "答复一",
                    "ttft_ms": 12_000.0,
                    "latency_ms": 55_000.0,
                    "issues": ["slow_turn"],
                },
                {
                    "turn": 2,
                    "query": "第二问",
                    "response": "答复二",
                    "ttft_ms": 8_000.0,
                    "latency_ms": 30_000.0,
                    "issues": [],
                },
            ],
        }
    ]

    rendered = MODULE._render_markdown(
        results,
        source_json=Path("/tmp/source.json"),
        teaching_mode="smart",
    )

    assert "平均 TTFT" in rendered
    assert "P50 TTFT" in rendered
    assert "P90 TTFT" in rendered
    assert "10000.0ms" in rendered


def test_build_turn_config_omits_eval_user_for_live_ws() -> None:
    runtime_config = MODULE._build_turn_config(
        query="测试问题",
        teaching_mode="smart",
        include_eval_user=True,
    )
    live_ws_config = MODULE._build_turn_config(
        query="测试问题",
        teaching_mode="smart",
        include_eval_user=False,
    )

    assert runtime_config["billing_context"]["user_id"] == "ld_eval_user"
    assert "user_id" not in live_ws_config["billing_context"]
    assert live_ws_config["billing_context"]["source"] == "wx_miniprogram"
    assert runtime_config["interaction_profile"] == "construction_exam_tutor"
    assert runtime_config["interaction_hints"]["profile"] == "construction_exam_tutor"
