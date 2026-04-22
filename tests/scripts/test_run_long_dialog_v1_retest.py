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
    async def _fake_run_single_turn(*_args, session_id=None, query: str, response_mode: str, **_kwargs):
        if "第一问" in query:
            return (
                session_id or "session-1",
                "答复一",
                12_000.0,
                55_000.0,
                ["content", "result"],
                {
                    "selected_mode": "deep",
                    "execution_path": "tutorbot_deep_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 2,
                },
            )
        return (
            session_id or "session-1",
            "答复二",
            8_000.0,
            30_000.0,
            ["content", "result"],
            {
                "selected_mode": "fast",
                "execution_path": "tutorbot_fast_policy",
                "exact_fast_path_hit": True,
                "actual_tool_rounds": 0,
            },
        )

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
        response_mode="smart",
        per_turn_timeout_s=5.0,
        turn_mode="full",
    )

    assert result["turns"][0]["ttft_ms"] == 12_000.0
    assert result["turns"][1]["ttft_ms"] == 8_000.0
    assert result["turns"][0]["selected_mode"] == "deep"
    assert result["turns"][1]["execution_path"] == "tutorbot_fast_policy"
    assert result["turns"][1]["exact_fast_path_hit"] is True
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
        response_mode="smart",
        api_base_url=None,
    )

    assert "平均 TTFT" in rendered
    assert "P50 TTFT" in rendered
    assert "P90 TTFT" in rendered
    assert "平均延迟" in rendered
    assert "10000.0ms" in rendered


def test_render_markdown_uses_turn_weighted_global_ttft_average() -> None:
    results = [
        {
            "case_id": "LD_SHORT",
            "title": "短 case",
            "source_session_id": "src-1",
            "summary": {
                "turns": 1,
                "hard_errors": 0,
                "followup_object_mismatch_count": 0,
                "question_count_mismatch_count": 0,
                "anchor_miss_count": 0,
                "context_reset_count": 0,
                "compare_table_miss_count": 0,
                "stale_replay_count": 0,
                "slow_turns": 0,
                "avg_latency_ms": 1000.0,
                "avg_ttft_ms": 100.0,
                "p50_ttft_ms": 100.0,
                "p90_ttft_ms": 100.0,
                "semantic_score": 100,
                "satisfaction_score": 100,
                "aborted": False,
                "abort_reason": "",
            },
            "turns": [
                {
                    "turn": 1,
                    "query": "第一问",
                    "response": "答复一",
                    "ttft_ms": 100.0,
                    "latency_ms": 1000.0,
                    "issues": [],
                }
            ],
        },
        {
            "case_id": "LD_LONG",
            "title": "长 case",
            "source_session_id": "src-2",
            "summary": {
                "turns": 3,
                "hard_errors": 0,
                "followup_object_mismatch_count": 0,
                "question_count_mismatch_count": 0,
                "anchor_miss_count": 0,
                "context_reset_count": 0,
                "compare_table_miss_count": 0,
                "stale_replay_count": 0,
                "slow_turns": 0,
                "avg_latency_ms": 1000.0,
                "avg_ttft_ms": 10.0,
                "p50_ttft_ms": 10.0,
                "p90_ttft_ms": 10.0,
                "semantic_score": 100,
                "satisfaction_score": 100,
                "aborted": False,
                "abort_reason": "",
            },
            "turns": [
                {
                    "turn": 1,
                    "query": "第二问",
                    "response": "答复二",
                    "ttft_ms": 10.0,
                    "latency_ms": 1000.0,
                    "issues": [],
                },
                {
                    "turn": 2,
                    "query": "第三问",
                    "response": "答复三",
                    "ttft_ms": 10.0,
                    "latency_ms": 1000.0,
                    "issues": [],
                },
                {
                    "turn": 3,
                    "query": "第四问",
                    "response": "答复四",
                    "ttft_ms": 10.0,
                    "latency_ms": 1000.0,
                    "issues": [],
                },
            ],
        },
    ]

    rendered = MODULE._render_markdown(
        results,
        source_json=Path("/tmp/source.json"),
        response_mode="smart",
        api_base_url=None,
    )

    assert "- 平均 TTFT: 32.5ms" in rendered


def test_build_turn_config_omits_eval_user_for_live_ws() -> None:
    runtime_config = MODULE._build_turn_config(
        query="测试问题",
        response_mode="smart",
        include_eval_user=True,
    )
    live_ws_config = MODULE._build_turn_config(
        query="测试问题",
        response_mode="smart",
        include_eval_user=False,
    )

    assert "billing_context" not in runtime_config
    assert "billing_context" not in live_ws_config
    assert runtime_config["interaction_profile"] == "tutorbot"
    assert runtime_config["bot_id"] == "construction-exam-coach"
    assert runtime_config["interaction_hints"]["profile"] == "tutorbot"


def test_classify_turn_normalizes_explicit_case_anchor_before_anchor_check() -> None:
    result = MODULE._classify_turn(
        query="你用盖一栋6层住宅楼举个例子讲讲",
        response="想象你盖一栋 6 层住宅楼，先做第一层，再做第二层。",
        latency_ms=1_000.0,
        prev_response="",
    )

    assert result["anchor_miss"] is False
    assert "anchor_miss:6层住宅楼" not in result["issues"]


@pytest.mark.asyncio
async def test_main_prints_ttft_summary_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_json = tmp_path / "source.json"
    source_json.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(MODULE, "_resolve_source_path", lambda _value: source_json)
    monkeypatch.setattr(
        MODULE,
        "_build_cases",
        lambda _payload: [{"case_id": "LD_TEST", "title": "stdout", "source_session_id": "src-1", "turns": []}],
    )

    async def _fake_run_case(*_args, **_kwargs):
        return {
            "case_id": "LD_TEST",
            "title": "stdout",
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
                "slow_turns": 0,
                "avg_latency_ms": 2000.0,
                "avg_ttft_ms": 1500.0,
                "p50_ttft_ms": 1500.0,
                "p90_ttft_ms": 1900.0,
                "semantic_score": 95,
                "satisfaction_score": 90,
                "aborted": False,
                "abort_reason": "",
            },
            "turns": [
                {"turn": 1, "query": "q1", "response": "a1", "ttft_ms": 1000.0, "latency_ms": 1800.0, "issues": []},
                {"turn": 2, "query": "q2", "response": "a2", "ttft_ms": 2000.0, "latency_ms": 2200.0, "issues": []},
            ],
        }

    monkeypatch.setattr(MODULE, "_run_case", _fake_run_case)
    monkeypatch.setattr(
        "argparse.ArgumentParser.parse_args",
        lambda _self: MODULE.argparse.Namespace(
            source_json=str(source_json),
            output_dir=str(tmp_path),
            cases=None,
            max_cases=None,
            turn_mode="full",
            response_mode="smart",
            legacy_teaching_mode=None,
            per_turn_timeout=5.0,
            api_base_url=None,
        ),
    )

    await MODULE.main()

    captured = capsys.readouterr()
    assert "平均 TTFT: 1500.0ms" in captured.out
    assert "P50 TTFT: 1500.0ms" in captured.out
    assert "P90 TTFT: 1900.0ms" in captured.out
    assert "平均延迟: 2000.0ms" in captured.out


@pytest.mark.asyncio
async def test_run_single_turn_leaves_capability_unforced_for_semantic_router() -> None:
    captured: dict[str, object] = {}

    class _FakeRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return {"id": "session-1"}, {"id": "turn-1"}

        async def subscribe_turn(self, _turn_id: str, after_seq: int = 0):
            del after_seq
            yield {"type": "session"}
            yield {"type": "content", "content": "答复"}
            yield {"type": "done"}

    session_id, response, ttft_ms, latency_ms, event_types, result_metadata = await MODULE._run_single_turn(
        _FakeRuntime(),
        session_id=None,
        query="给我出两道选择题",
        response_mode="smart",
    )

    assert captured["payload"]["capability"] is None
    assert session_id == "session-1"
    assert response == "答复"
    assert ttft_ms is not None
    assert latency_ms >= 0
    assert event_types == ["session", "content", "done"]
    assert result_metadata == {}


@pytest.mark.asyncio
async def test_run_single_turn_keeps_tutorbot_for_non_generation_turns() -> None:
    captured: dict[str, object] = {}

    class _FakeRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return {"id": "session-1"}, {"id": "turn-1"}

        async def subscribe_turn(self, _turn_id: str, after_seq: int = 0):
            del after_seq
            yield {"type": "done"}

    await MODULE._run_single_turn(
        _FakeRuntime(),
        session_id=None,
        query="你用盖一栋6层住宅楼举个例子讲讲",
        response_mode="smart",
    )

    assert captured["payload"]["capability"] == "tutorbot"


@pytest.mark.asyncio
async def test_run_single_turn_unpins_tutorbot_when_question_followup_context_exists() -> None:
    captured: dict[str, object] = {}

    class _FakeRuntime:
        async def start_turn(self, payload):
            captured["payload"] = payload
            return {"id": "session-1"}, {"id": "turn-1"}

        async def subscribe_turn(self, _turn_id: str, after_seq: int = 0):
            del after_seq
            yield {"type": "done"}

    await MODULE._run_single_turn(
        _FakeRuntime(),
        session_id="session-1",
        query="我答一下：第1题选B，第2题选C。你帮我批改，并且针对我错的地方解释一下。",
        response_mode="smart",
        followup_question_context={
            "question_id": "q_1",
            "question": "### Question 1",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题目1",
                    "question_type": "choice",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                },
                {
                    "question_id": "q_2",
                    "question": "题目2",
                    "question_type": "choice",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                },
            ],
        },
    )

    assert captured["payload"]["capability"] is None


@pytest.mark.asyncio
async def test_run_single_turn_live_ws_keeps_capability_unforced() -> None:
    captured: dict[str, object] = {}

    class _FakeWebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def send(self, payload: str):
            captured["payload"] = json.loads(payload)

        async def recv(self):
            return json.dumps({"type": "done"})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(MODULE.websockets, "connect", lambda _url: _FakeWebSocket())

    await MODULE._run_single_turn_live_ws(
        api_base_url="http://127.0.0.1:8001",
        session_id=None,
        query="你用盖一栋6层住宅楼举个例子讲讲",
        response_mode="smart",
    )

    assert captured["payload"]["capability"] is None
    monkeypatch.undo()
