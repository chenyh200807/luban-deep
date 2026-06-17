"""Heartbeat cross-worker single-instance gate — under uvicorn --workers N, only one
worker's periodic tick may run (no duplicate LLM call / duplicate workspace writes)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from deeptutor.tutorbot.heartbeat import service as hb


def _make(tmp_path: Path, key: str | None) -> hb.HeartbeatService:
    return hb.HeartbeatService(
        workspace=tmp_path,
        provider=SimpleNamespace(),
        model="m",
        single_instance_key=key,
    )


def test_no_key_always_runs(tmp_path: Path) -> None:
    assert _make(tmp_path, None)._claim_tick_window() is True


def test_fail_open_when_no_redis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hb, "_heartbeat_redis", lambda: None)
    assert _make(tmp_path, "bot1")._claim_tick_window() is True


def test_only_one_worker_wins_the_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A tiny fake valkey: SET NX succeeds once per key, then fails (lock held).
    class _FakeRedis:
        def __init__(self) -> None:
            self._keys: set[str] = set()

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self._keys:
                return None  # already held
            self._keys.add(key)
            return True

    shared = _FakeRedis()
    monkeypatch.setattr(hb, "_heartbeat_redis", lambda: shared)

    worker_a = _make(tmp_path, "construction_exam_bot")
    worker_b = _make(tmp_path, "construction_exam_bot")
    assert worker_a._claim_tick_window() is True    # first worker claims the window
    assert worker_b._claim_tick_window() is False   # second worker skips (duplicate prevented)


def test_fail_open_on_redis_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomRedis:
        def set(self, *a, **k):
            raise RuntimeError("valkey down")

    monkeypatch.setattr(hb, "_heartbeat_redis", lambda: _BoomRedis())
    # Redis hiccup must not silence the heartbeat — fail-open (run).
    assert _make(tmp_path, "bot1")._claim_tick_window() is True
