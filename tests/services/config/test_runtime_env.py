from __future__ import annotations

from deeptutor.services import runtime_env


class _FakeEnvStore:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_runtime_environment_reads_through_env_store(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore({"APP_ENV": "production"}),
    )

    assert runtime_env.runtime_environment() == "production"
    assert runtime_env.is_production_environment() is True


def test_env_flag_reads_through_env_store_and_honors_default(monkeypatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "FLAG_TRUE": "yes",
                "FLAG_FALSE": "off",
                "FLAG_UNKNOWN": "sometimes",
            }
        ),
    )

    assert runtime_env.env_flag("FLAG_TRUE", default=False) is True
    assert runtime_env.env_flag("FLAG_FALSE", default=True) is False
    assert runtime_env.env_flag("FLAG_UNKNOWN", default=True) is True
    assert runtime_env.env_flag("FLAG_MISSING", default=False) is False
