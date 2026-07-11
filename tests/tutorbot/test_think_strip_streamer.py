"""Battle1 W1-T4: oracle-locked equivalence tests for _ThinkStripStreamer.

The oracle is a verbatim replay of the OLD _stream_delta implementation
(full-buffer regex cascade + emitted-length clip), per the commander ruling:
the comparison target is the old emission *sequence* (buffer + clip
semantics), NOT ``old_regex(full_text)`` — those two differ in shrink
scenarios (e.g. plain ``<x>`` text emitted before an orphan ``</think>``
arrives), and already-emitted characters are never retracted.
"""

from __future__ import annotations

import random
import re

from deeptutor.tutorbot.agent.loop import _ThinkStripStreamer


class _OldOracle:
    """Verbatim replay of the pre-Battle1 implementation (bug-for-bug)."""

    def __init__(self) -> None:
        self.raw = ""
        self.emitted_len = 0

    @staticmethod
    def _visible(raw_text: str) -> str:
        visible = re.sub(r"<think>[\s\S]*?</think>", "", raw_text)
        visible = re.sub(r"<think>[\s\S]*$", "", visible)
        visible = re.sub(r"</think>[\s\S]*$", "", visible)
        visible = re.sub(r"<[^>]*$", "", visible)
        return visible

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        self.raw += delta
        visible = self._visible(self.raw)
        if len(visible) <= self.emitted_len:
            return ""
        chunk = visible[self.emitted_len:]
        self.emitted_len = len(visible)
        return chunk


_SEGMENTS = [
    "<think>",
    "</think>",
    "<",
    ">",
    "think",
    "/think",
    "文字abc ",
    "疏散楼梯间净宽度1.10m。",
    "\n",
    "<thi",
    "nk>",
    "</th",
    "ink>",
    "x<y>z",
    "5m深基坑<b需要论证",
    "plain english words ",
    "<a",
    "b>",
    "<div>html</div>",
    "</think",
    "k>t",
]


def _random_stream(rng: random.Random) -> list[str]:
    text = "".join(rng.choice(_SEGMENTS) for _ in range(rng.randint(1, 24)))
    deltas: list[str] = []
    i = 0
    while i < len(text):
        step = rng.randint(1, 9)
        deltas.append(text[i : i + step])
        i += step
    return deltas


def test_fuzz_parity_with_old_implementation() -> None:
    rng = random.Random(20260711)
    for case in range(600):
        oracle = _OldOracle()
        streamer = _ThinkStripStreamer()
        deltas = _random_stream(rng)
        for step, delta in enumerate(deltas):
            expected = oracle.feed(delta)
            actual = streamer.feed(delta)
            assert actual == expected, (
                f"case={case} step={step} delta={delta!r}\n"
                f"raw so far={oracle.raw!r}\n"
                f"expected={expected!r} actual={actual!r}"
            )


def test_prefix_monotonic_never_retracts() -> None:
    rng = random.Random(42)
    for _ in range(200):
        streamer = _ThinkStripStreamer()
        cumulative = ""
        for delta in _random_stream(rng):
            chunk = streamer.feed(delta)
            new_cumulative = cumulative + chunk
            assert new_cumulative.startswith(cumulative)
            cumulative = new_cumulative


def test_plain_text_passes_through_unchanged() -> None:
    streamer = _ThinkStripStreamer()
    out = "".join(streamer.feed(d) for d in ["你好", "，这是", "普通回答。"])
    assert out == "你好，这是普通回答。"


def test_think_block_hidden_and_following_text_visible() -> None:
    streamer = _ThinkStripStreamer()
    deltas = ["前言", "<think>内部", "推理", "</think>", "结论"]
    out = "".join(streamer.feed(d) for d in deltas)
    assert out == "前言结论"


def test_orphan_close_suppresses_rest_forever() -> None:
    streamer = _ThinkStripStreamer()
    out = "".join(streamer.feed(d) for d in ["可见", "</think>", "永不可见", "<think>x</think>y"])
    assert out == "可见"


def test_split_tags_across_deltas() -> None:
    streamer = _ThinkStripStreamer()
    deltas = ["答案<th", "ink>hidden</thi", "nk>可见部分"]
    out = "".join(streamer.feed(d) for d in deltas)
    assert out == "答案可见部分"


def test_incremental_cost_is_linear_smoke() -> None:
    import time

    streamer = _ThinkStripStreamer()
    delta = "疏散楼梯间的净宽度不应小于一点一零米，" * 2
    start = time.perf_counter()
    for _ in range(5000):  # ~200KB total, previously O(n^2) rescans
        streamer.feed(delta)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"5000 deltas took {elapsed:.2f}s"
