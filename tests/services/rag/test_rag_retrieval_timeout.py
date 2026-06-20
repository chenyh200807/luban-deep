from __future__ import annotations

import pytest

from deeptutor.services.rag.pipelines.llamaindex import _rag_retrieval_timeout_seconds


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


def test_rag_retrieval_timeout_default(monkeypatch) -> None:
    _patch(monkeypatch, {})
    assert _rag_retrieval_timeout_seconds() == 30.0


def test_rag_retrieval_timeout_env_override(monkeypatch) -> None:
    _patch(monkeypatch, {"DEEPTUTOR_RAG_RETRIEVAL_TIMEOUT_SECONDS": "45"})
    assert _rag_retrieval_timeout_seconds() == 45.0


def test_rag_retrieval_timeout_floor_and_cap_and_bad(monkeypatch) -> None:
    _patch(monkeypatch, {"DEEPTUTOR_RAG_RETRIEVAL_TIMEOUT_SECONDS": "1"})
    assert _rag_retrieval_timeout_seconds() == 5.0
    _patch(monkeypatch, {"DEEPTUTOR_RAG_RETRIEVAL_TIMEOUT_SECONDS": "9999"})
    assert _rag_retrieval_timeout_seconds() == 120.0
    _patch(monkeypatch, {"DEEPTUTOR_RAG_RETRIEVAL_TIMEOUT_SECONDS": "x"})
    assert _rag_retrieval_timeout_seconds() == 30.0
