from __future__ import annotations

from deeptutor.services.internal_qa import (
    EVAL_BILLING_BYPASS_MAX_SKEW_SECONDS,
    eval_billing_bypass_configured,
    eval_billing_bypass_signature_valid,
    internal_qa_billing_bypass_allowed,
    internal_qa_billing_bypass_enabled,
    make_eval_billing_bypass_token,
)


class _FakeEnvStore:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


# A 64-char key clears the minimum-strength floor; production-style secret.
_EVAL_KEY = "a" * 64


def _patch_env(monkeypatch, values: dict[str, str]) -> None:
    monkeypatch.setattr(
        "deeptutor.services.config.env_store.get_env_store",
        lambda: _FakeEnvStore(values),
    )


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


# --- eval-mode billing bypass (key-gated, production-capable) ---


def test_eval_bypass_impossible_without_key_even_in_non_production(monkeypatch) -> None:
    # No key configured -> fail closed everywhere, including non-production.
    _patch_env(monkeypatch, {"DEEPTUTOR_ENV": "local"})
    assert eval_billing_bypass_configured() is False
    token = make_eval_billing_bypass_token(_EVAL_KEY, ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(token, "qa_student", now=1_000_000) is False
    )


def test_eval_bypass_short_key_is_treated_as_unset(monkeypatch) -> None:
    _patch_env(monkeypatch, {"DEEPTUTOR_EVAL_BYPASS_KEY": "tooshort"})
    assert eval_billing_bypass_configured() is False
    token = make_eval_billing_bypass_token("tooshort", ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(token, "qa_student", now=1_000_000) is False
    )


def test_eval_bypass_valid_signature_in_production(monkeypatch) -> None:
    # Even in production, a valid signature + key + QA identity is accepted.
    _patch_env(
        monkeypatch,
        {"DEEPTUTOR_ENV": "production", "DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY},
    )
    token = make_eval_billing_bypass_token(_EVAL_KEY, ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(token, "qa_studentarmy_1", now=1_000_000)
        is True
    )


def test_eval_bypass_rejects_forged_signature(monkeypatch) -> None:
    _patch_env(monkeypatch, {"DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY})
    forged = make_eval_billing_bypass_token("b" * 64, ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(forged, "qa_student", now=1_000_000)
        is False
    )


def test_eval_bypass_rejects_expired_token(monkeypatch) -> None:
    _patch_env(monkeypatch, {"DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY})
    token = make_eval_billing_bypass_token(_EVAL_KEY, ts=1_000_000)
    stale_now = 1_000_000 + EVAL_BILLING_BYPASS_MAX_SKEW_SECONDS + 1
    assert eval_billing_bypass_signature_valid(token, "qa_student", now=stale_now) is False


def test_eval_bypass_rejects_non_qa_identity_protecting_real_users(monkeypatch) -> None:
    # A valid signature must never bypass a real (non-cohort) paying user.
    _patch_env(monkeypatch, {"DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY})
    token = make_eval_billing_bypass_token(_EVAL_KEY, ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(token, "paying_user_42", now=1_000_000)
        is False
    )


def test_eval_bypass_username_allowlist_narrows_scope(monkeypatch) -> None:
    _patch_env(
        monkeypatch,
        {
            "DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY,
            "DEEPTUTOR_EVAL_BYPASS_USERS": "qa_allowed_one, qa_allowed_two",
        },
    )
    token = make_eval_billing_bypass_token(_EVAL_KEY, ts=1_000_000)
    assert (
        eval_billing_bypass_signature_valid(token, "qa_allowed_one", now=1_000_000)
        is True
    )
    # In-cohort but not on the allowlist -> rejected.
    assert (
        eval_billing_bypass_signature_valid(token, "qa_not_listed", now=1_000_000)
        is False
    )


def test_eval_bypass_rejects_malformed_token(monkeypatch) -> None:
    _patch_env(monkeypatch, {"DEEPTUTOR_EVAL_BYPASS_KEY": _EVAL_KEY})
    for bad in ("", "garbage", "v1.notanint.deadbeef", "v2.1000000.deadbeef"):
        assert (
            eval_billing_bypass_signature_valid(bad, "qa_student", now=1_000_000)
            is False
        )
