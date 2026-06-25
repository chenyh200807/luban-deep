from __future__ import annotations

from deeptutor.services.observability import metrics_loader


class _FakeEnvStore:
    def __init__(self, token: str) -> None:
        self._token = token

    def get(self, key: str, default: str = "") -> str:
        if key == "DEEPTUTOR_METRICS_TOKEN":
            return self._token
        return default


def test_resolve_metrics_token_falls_back_to_env_store(monkeypatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_METRICS_TOKEN", raising=False)
    monkeypatch.setattr(metrics_loader, "get_env_store", lambda: _FakeEnvStore("token-from-dotenv"))

    assert metrics_loader.resolve_metrics_token() == "token-from-dotenv"
