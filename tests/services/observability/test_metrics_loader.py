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


def test_governed_metrics_urls_use_only_dedicated_public_https_registry(monkeypatch) -> None:
    monkeypatch.setattr(
        metrics_loader.socket,
        "getaddrinfo",
        lambda host, port, **_kwargs: [
            (
                metrics_loader.socket.AF_INET,
                metrics_loader.socket.SOCK_STREAM,
                6,
                "",
                (
                    "93.184.216.34" if host == "test2.example" else "127.0.0.1",
                    port,
                ),
            )
        ],
    )
    monkeypatch.delenv("DEEPTUTOR_OBSERVABILITY_GOVERNED_API_BASE_URLS", raising=False)
    monkeypatch.setenv("WECHAT_QA_BASE_URL", "http://127.0.0.1:8001")
    monkeypatch.setattr(metrics_loader, "get_env_store", lambda: _FakeEnvStore(""))
    assert metrics_loader.resolve_governed_metrics_urls() == ()

    monkeypatch.setenv(
        "DEEPTUTOR_OBSERVABILITY_GOVERNED_API_BASE_URLS",
        "https://test2.example, http://127.0.0.1:8001, https://localhost:8443",
    )
    assert metrics_loader.resolve_governed_metrics_urls() == (
        "https://test2.example/metrics",
    )


def test_governed_metrics_urls_reject_dns_and_decimal_loopback_aliases(monkeypatch) -> None:
    monkeypatch.setattr(metrics_loader, "get_env_store", lambda: _FakeEnvStore(""))
    monkeypatch.setattr(
        metrics_loader.socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            (
                metrics_loader.socket.AF_INET,
                metrics_loader.socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", port),
            )
        ],
    )
    monkeypatch.setenv(
        "DEEPTUTOR_OBSERVABILITY_GOVERNED_API_BASE_URLS",
        "https://2130706433:8001,https://127.0.0.1.nip.io:8001",
    )

    assert metrics_loader.resolve_governed_metrics_urls() == ()
