"""Hermetic tests for the M35 R2 live judge adapters (no real HTTP/subprocess).

Only adapter parsing, abstention, caching, stats, and factory wiring are
tested here. Transport seams (``_http_post_json`` / ``_run_cli``) are always
monkeypatched; a real provider call in this file is a bug.
"""

import json

import pytest

from scripts import m35_gold_judges as judges
from scripts.m35_gold_judges import (
    JudgeStats,
    JudgeTransportError,
    build_judge_prompt,
    build_live_judges,
    load_dotenv_file,
    make_claude_judge,
    make_codex_judge,
    make_deepseek_judge,
    make_qwen_judge,
    parse_codex_jsonl,
    parse_judge_output,
)

POINT = {
    "point_id": "Q2023-01__P01::SP01",
    "criterion": "不妥之处：试验员制作见证记录；正确做法：应由见证人员制作见证记录。",
    "max_score": 3.5,
}
ANCHOR = {"question_id": "Q2023-01__P01", "stem": "【背景资料】某新建住宅小区……【问题】指出不妥之处。"}
ANSWER = "试验员制作见证记录不妥，应由见证人员制作。"
GOOD_JSON = '{"verdict":"hit","evidence_span":"应由见证人员制作","confidence":0.9}'


def _chat_body(content: str, usage: dict | None = None) -> dict:
    body = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


# ---------------------------------------------------------------- parsing


def test_parse_judge_output_accepts_plain_json():
    parsed = parse_judge_output(GOOD_JSON)
    assert parsed == {"verdict": "hit", "evidence_span": "应由见证人员制作", "confidence": 0.9}


def test_parse_judge_output_accepts_fenced_and_prose_wrapped_json():
    fenced = f"```json\n{GOOD_JSON}\n```"
    assert parse_judge_output(fenced)["verdict"] == "hit"
    prose = f"好的，判定结果如下：{GOOD_JSON} 以上。"
    assert parse_judge_output(prose)["verdict"] == "hit"


def test_parse_judge_output_handles_braces_inside_evidence_string():
    text = '{"verdict":"partial","evidence_span":"片段{含括号}","confidence":0.5}'
    assert parse_judge_output(text)["evidence_span"] == "片段{含括号}"


def test_parse_judge_output_rejects_invalid_verdict_or_garbage():
    assert parse_judge_output('{"verdict":"correct","evidence_span":"","confidence":1}') is None
    assert parse_judge_output("完全不是 JSON") is None
    assert parse_judge_output("") is None


def test_parse_judge_output_coerces_and_clamps_fields():
    parsed = parse_judge_output('{"verdict":"miss","confidence":"1.7"}')
    assert parsed == {"verdict": "miss", "evidence_span": "", "confidence": 1.0}
    parsed = parse_judge_output('{"verdict":"miss","confidence":-2}')
    assert parsed["confidence"] == 0.0


def test_parse_codex_jsonl_new_style_events():
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": GOOD_JSON}}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 26014, "cached_input_tokens": 4480, "output_tokens": 62},
                }
            ),
        ]
    )
    message, usage = parse_codex_jsonl(stdout)
    assert message == GOOD_JSON
    assert usage == {"prompt_tokens": 26014, "completion_tokens": 62, "total_tokens": 26076}


def test_parse_codex_jsonl_legacy_msg_events_and_garbage_lines():
    stdout = "\n".join(
        [
            "not-json at all",
            json.dumps({"id": "1", "msg": {"type": "agent_message", "message": "early"}}),
            json.dumps({"id": "2", "msg": {"type": "agent_message", "message": GOOD_JSON}}),
            json.dumps(
                {
                    "id": "3",
                    "msg": {
                        "type": "token_count",
                        "info": {"total_token_usage": {"input_tokens": 10, "output_tokens": 5}},
                    },
                }
            ),
        ]
    )
    message, usage = parse_codex_jsonl(stdout)
    assert message == GOOD_JSON  # last agent message wins
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_parse_codex_jsonl_without_agent_message_returns_none():
    message, usage = parse_codex_jsonl(json.dumps({"type": "turn.started"}))
    assert message is None
    assert usage is None


def test_build_judge_prompt_anchors_official_criterion():
    prompt = build_judge_prompt(POINT, ANSWER, ANCHOR)
    assert POINT["criterion"] in prompt
    assert ANSWER in prompt
    assert ANCHOR["stem"] in prompt
    assert "3.5" in prompt
    for token in ("hit", "partial", "miss", "JSON"):
        assert token in prompt


def test_load_dotenv_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nexport DEEPSEEK_API_KEY=sk-abc\nDASHSCOPE_API_KEY='sk-q'\nBROKEN_LINE\nQUOTED=\"v\"\n",
        encoding="utf-8",
    )
    parsed = load_dotenv_file(env_file)
    assert parsed["DEEPSEEK_API_KEY"] == "sk-abc"
    assert parsed["DASHSCOPE_API_KEY"] == "sk-q"
    assert parsed["QUOTED"] == "v"
    assert "BROKEN_LINE" not in parsed
    assert load_dotenv_file(tmp_path / "missing.env") == {}


# ---------------------------------------------------------------- HTTP judges


def test_deepseek_judge_parses_verdict_and_records_usage(monkeypatch):
    calls = []

    def fake_post(url, headers, payload, timeout):
        calls.append((url, payload["model"], timeout))
        assert headers["Authorization"] == "Bearer sk-test"
        return _chat_body(GOOD_JSON, {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})

    monkeypatch.setattr(judges, "_http_post_json", fake_post)
    stats = JudgeStats()
    judge = make_deepseek_judge("sk-test", stats)
    vote = judge(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "hit"
    assert calls[0][1] == "deepseek-chat"
    assert calls[0][2] == judges.JUDGE_TIMEOUT_SECONDS
    snap = stats.snapshot()["deepseek-chat"]
    assert snap["calls"] == 1
    assert snap["abstains"] == 0
    assert snap["prompt_tokens"] == 100
    assert snap["completion_tokens"] == 20
    assert snap["estimated_cost_usd"] is not None and snap["estimated_cost_usd"] > 0


def test_qwen_judge_uses_dashscope_compatible_endpoint(monkeypatch):
    seen = {}

    def fake_post(url, headers, payload, timeout):
        seen["url"] = url
        seen["model"] = payload["model"]
        return _chat_body(GOOD_JSON)

    monkeypatch.setattr(judges, "_http_post_json", fake_post)
    stats = JudgeStats()
    vote = make_qwen_judge("sk-q", stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "hit"
    assert "dashscope.aliyuncs.com/compatible-mode" in seen["url"]
    assert seen["model"] == "qwen-max"


def test_http_judge_abstains_on_transport_error_and_unparseable_output(monkeypatch):
    stats = JudgeStats()

    monkeypatch.setattr(
        judges, "_http_post_json", lambda *a, **k: (_ for _ in ()).throw(JudgeTransportError("timeout after 60s"))
    )
    vote = make_deepseek_judge("sk-test", stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "abstain"
    assert "timeout" in vote["abstain_reason"]

    monkeypatch.setattr(judges, "_http_post_json", lambda *a, **k: _chat_body("我无法给出 JSON"))
    vote = make_deepseek_judge("sk-test", stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "abstain"
    assert vote["abstain_reason"] == "unparseable_output"

    snap = stats.snapshot()["deepseek-chat"]
    assert snap["calls"] == 2
    assert snap["abstains"] == 2
    assert snap["abstain_rate"] == 1.0


def test_http_judge_abstain_never_raises_and_never_fabricates(monkeypatch):
    monkeypatch.setattr(
        judges, "_http_post_json", lambda *a, **k: {"choices": []}
    )
    vote = make_qwen_judge("sk-q", JudgeStats())(POINT, ANSWER, ANCHOR)
    assert vote == {
        "verdict": "abstain",
        "evidence_span": "",
        "confidence": 0.0,
        "abstain_reason": vote["abstain_reason"],
    }


# ---------------------------------------------------------------- CLI judges


def test_codex_judge_builds_command_and_parses_jsonl(monkeypatch):
    seen = {}

    def fake_run_cli(cmd, timeout, cwd=None):
        seen["cmd"] = cmd
        seen["timeout"] = timeout
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": GOOD_JSON}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 10}}),
            ]
        )
        return 0, stdout, ""

    monkeypatch.setattr(judges, "_run_cli", fake_run_cli)
    stats = JudgeStats()
    vote = make_codex_judge(stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "hit"
    assert seen["cmd"][:2] == ["codex", "exec"]
    assert "--json" in seen["cmd"]
    assert "read-only" in seen["cmd"]
    assert seen["timeout"] == judges.JUDGE_TIMEOUT_SECONDS
    snap = stats.snapshot()["gpt-codex"]
    assert snap["total_tokens"] == 60


def test_codex_judge_abstains_on_nonzero_exit_timeout_and_missing_message(monkeypatch):
    stats = JudgeStats()

    monkeypatch.setattr(judges, "_run_cli", lambda *a, **k: (1, "", "boom"))
    assert make_codex_judge(stats)(POINT, ANSWER, ANCHOR)["verdict"] == "abstain"

    # The real failure cause lives in the stdout JSONL error event (e.g. usage
    # limits); the abstain reason must surface it, not the stderr noise.
    quota_stdout = "\n".join(
        [
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "error", "message": "You've hit your usage limit."}),
        ]
    )
    monkeypatch.setattr(
        judges,
        "_run_cli",
        lambda *a, **k: (1, quota_stdout, "Reading additional input from stdin..."),
    )
    vote = make_codex_judge(stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "abstain"
    assert "usage limit" in vote["abstain_reason"]

    monkeypatch.setattr(
        judges, "_run_cli", lambda *a, **k: (_ for _ in ()).throw(JudgeTransportError("timeout after 60s"))
    )
    assert make_codex_judge(stats)(POINT, ANSWER, ANCHOR)["verdict"] == "abstain"

    monkeypatch.setattr(judges, "_run_cli", lambda *a, **k: (0, json.dumps({"type": "turn.started"}), ""))
    assert make_codex_judge(stats)(POINT, ANSWER, ANCHOR)["verdict"] == "abstain"

    assert stats.snapshot()["gpt-codex"]["abstains"] == 4


def test_claude_judge_builds_command_and_parses_text(monkeypatch):
    seen = {}

    def fake_run_cli(cmd, timeout, cwd=None):
        seen["cmd"] = cmd
        return 0, GOOD_JSON + "\n", ""

    monkeypatch.setattr(judges, "_run_cli", fake_run_cli)
    stats = JudgeStats()
    vote = make_claude_judge("opus", "claude-opus-4-8", stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "hit"
    cmd = seen["cmd"]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-8"
    assert cmd[cmd.index("--output-format") + 1] == "text"
    snap = stats.snapshot()["opus"]
    assert snap["calls"] == 1
    assert snap["total_tokens"] == 0  # text format exposes no usage
    assert snap["estimated_cost_usd"] is None


def test_claude_judge_abstains_on_garbage_output(monkeypatch):
    monkeypatch.setattr(judges, "_run_cli", lambda *a, **k: (0, "抱歉，我需要更多信息。", ""))
    stats = JudgeStats()
    vote = make_claude_judge("fable", "claude-fable-5", stats)(POINT, ANSWER, ANCHOR)
    assert vote["verdict"] == "abstain"
    assert stats.snapshot()["fable"]["abstain_rate"] == 1.0


def test_judge_cache_reuses_identical_prompt_results(monkeypatch):
    call_count = {"n": 0}

    def fake_post(url, headers, payload, timeout):
        call_count["n"] += 1
        return _chat_body(GOOD_JSON, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    monkeypatch.setattr(judges, "_http_post_json", fake_post)
    stats = JudgeStats()
    judge = make_deepseek_judge("sk-test", stats)
    first = judge(POINT, ANSWER, ANCHOR)
    second = judge(POINT, ANSWER, ANCHOR)
    assert call_count["n"] == 1
    assert first == second
    judge(POINT, "完全不同的作答", ANCHOR)
    assert call_count["n"] == 2
    snap = stats.snapshot()["deepseek-chat"]
    assert snap["calls"] == 3
    assert snap["cached_hits"] == 1
    assert snap["total_tokens"] == 30  # cached call accumulates no new tokens


def test_abstain_results_are_not_cached(monkeypatch):
    attempts = {"n": 0}

    def flaky_post(url, headers, payload, timeout):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise JudgeTransportError("connection reset")
        return _chat_body(GOOD_JSON)

    monkeypatch.setattr(judges, "_http_post_json", flaky_post)
    judge = make_deepseek_judge("sk-test", JudgeStats())
    assert judge(POINT, ANSWER, ANCHOR)["verdict"] == "abstain"
    assert judge(POINT, ANSWER, ANCHOR)["verdict"] == "hit"


# ---------------------------------------------------------------- factory


def test_build_live_judges_requires_all_prerequisites(monkeypatch):
    monkeypatch.setattr(judges.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError) as exc_info:
        build_live_judges(env={})
    message = str(exc_info.value)
    assert "DEEPSEEK_API_KEY" in message
    assert "DASHSCOPE_API_KEY" in message
    assert "codex" in message
    assert "claude" in message


def test_build_live_judges_returns_five_judges_and_stats(monkeypatch):
    monkeypatch.setattr(judges.shutil, "which", lambda name: f"/fake/bin/{name}")
    judge_fns, stats = build_live_judges(
        env={"DEEPSEEK_API_KEY": "sk-d", "DASHSCOPE_API_KEY": "sk-q"}
    )
    assert sorted(judge_fns) == ["deepseek-chat", "fable", "gpt-codex", "opus", "qwen-max"]
    assert all(callable(fn) for fn in judge_fns.values())
    assert isinstance(stats, JudgeStats)


def test_build_live_judges_explicit_env_ignores_dotenv(monkeypatch, tmp_path):
    # An explicit env mapping must be treated as the complete environment;
    # repo .env must not leak keys into hermetic callers.
    monkeypatch.setattr(judges.shutil, "which", lambda name: f"/fake/bin/{name}")
    monkeypatch.setattr(judges, "DOTENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-real\nDASHSCOPE_API_KEY=sk-real\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        build_live_judges(env={"DEEPSEEK_API_KEY": ""})
