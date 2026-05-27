from __future__ import annotations

import pytest

from deeptutor.services.benchmark.cassette import Cassette, llm_key, tool_key


def test_llm_key_is_stable_and_param_order_independent() -> None:
    k1 = llm_key(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "hi"}],
        params={"temperature": 0, "max_tokens": 10},
    )
    k2 = llm_key(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "hi"}],
        params={"max_tokens": 10, "temperature": 0},
    )
    assert k1 == k2


def test_llm_key_changes_with_model_and_messages() -> None:
    base = dict(messages=[{"role": "user", "content": "q"}], params={})
    assert llm_key(model="m1", **base) != llm_key(model="m2", **base)
    assert llm_key(
        model="m", messages=[{"role": "user", "content": "a"}], params={}
    ) != llm_key(model="m", messages=[{"role": "user", "content": "b"}], params={})


def test_cassette_records_and_replays_llm() -> None:
    c = Cassette()
    k = llm_key(model="m", messages=[{"role": "user", "content": "q"}], params={})
    c.record_llm(k, "ANSWER")
    assert c.replay_llm(k) == "ANSWER"


def test_cassette_records_and_replays_tool() -> None:
    c = Cassette()
    k = tool_key(name="rag", args={"query": "x"})
    c.record_tool(k, {"sources": [1, 2]})
    assert c.replay_tool(k) == {"sources": [1, 2]}


def test_replay_miss_raises() -> None:
    with pytest.raises(KeyError):
        Cassette().replay_llm("absent")
    with pytest.raises(KeyError):
        Cassette().replay_tool("absent")


def test_cassette_round_trips_through_json() -> None:
    c = Cassette()
    c.record_llm("k1", "r1")
    c.record_tool("t1", {"ok": True})
    restored = Cassette.from_json(c.to_json())
    assert restored.replay_llm("k1") == "r1"
    assert restored.replay_tool("t1") == {"ok": True}
