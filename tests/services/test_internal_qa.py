from __future__ import annotations

from deeptutor.services.internal_qa import (
    internal_qa_billing_bypass_allowed,
    internal_qa_billing_bypass_enabled,
)


class _FakeEnvStore:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_internal_qa_billing_bypass_enabled_only_outside_production(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "DEEPTUTOR_ENV": "local",
                "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS": "true",
            }
        ),
    )

    assert internal_qa_billing_bypass_enabled() is True


def test_internal_qa_billing_bypass_allowed_for_qa_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "DEEPTUTOR_ENV": "local",
                "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS": "true",
            }
        ),
    )

    assert internal_qa_billing_bypass_allowed("qa_student_001") is True


def test_internal_qa_billing_bypass_rejects_non_qa_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "DEEPTUTOR_ENV": "local",
                "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS": "true",
            }
        ),
    )

    assert internal_qa_billing_bypass_allowed("student_demo") is False


def test_internal_qa_billing_bypass_is_disabled_in_production(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "DEEPTUTOR_ENV": "production",
                "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS": "true",
            }
        ),
    )

    assert internal_qa_billing_bypass_enabled() is False


def test_internal_qa_billing_bypass_is_disabled_with_runtime_env_production(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(
            {
                "DEEPTUTOR_RUNTIME_ENV": "production",
                "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS": "true",
            }
        ),
    )

    assert internal_qa_billing_bypass_enabled() is False
