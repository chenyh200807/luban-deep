from __future__ import annotations

from deeptutor.tutorbot.providers.base import _first_token_timeout_seconds


class _FakeEnvStore:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def _patch(monkeypatch, values: dict[str, str]) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(values),
    )


def test_first_token_timeout_default(monkeypatch) -> None:
    _patch(monkeypatch, {})
    # Default 35s, far below the 90s inter-chunk idle: a never-starting stream
    # fails fast into the retry/terminal path instead of a 90s blank turn.
    assert _first_token_timeout_seconds(90) == 35.0


def test_first_token_timeout_never_exceeds_idle(monkeypatch) -> None:
    _patch(monkeypatch, {})
    # First-token bound is clamped to the idle timeout (can't be slower than a
    # mid-stream stall).
    assert _first_token_timeout_seconds(20) == 20.0


def test_first_token_timeout_env_override(monkeypatch) -> None:
    _patch(monkeypatch, {"DEEPTUTOR_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "50"})
    assert _first_token_timeout_seconds(90) == 50.0


def test_first_token_timeout_floor_and_bad_value(monkeypatch) -> None:
    _patch(monkeypatch, {"DEEPTUTOR_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "1"})
    assert _first_token_timeout_seconds(90) == 5.0  # floor
    _patch(monkeypatch, {"DEEPTUTOR_LLM_FIRST_TOKEN_TIMEOUT_SECONDS": "garbage"})
    assert _first_token_timeout_seconds(90) == 35.0  # falls back to default
