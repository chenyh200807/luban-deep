from __future__ import annotations

from scripts.check_secret_envs import main, validate_secret_envs


def test_prod_secret_missing_fails_closed() -> None:
    ok, messages = validate_secret_envs("prod", {})

    assert ok is False
    assert "DEEPTUTOR_ATTEMPT_REF_SECRET=missing" in messages


def test_prod_dev_secret_fails_closed() -> None:
    ok, messages = validate_secret_envs("production", {"DEEPTUTOR_ATTEMPT_REF_SECRET": "dev-attempt-ref-secret"})

    assert ok is False
    assert "DEEPTUTOR_ATTEMPT_REF_SECRET=dev-secret-forbidden" in messages


def test_prod_short_secret_fails_closed() -> None:
    ok, messages = validate_secret_envs("prod", {"DEEPTUTOR_ATTEMPT_REF_SECRET": "short"})

    assert ok is False
    assert "DEEPTUTOR_ATTEMPT_REF_SECRET=too-short" in messages


def test_prod_valid_secret_reports_fingerprint() -> None:
    ok, messages = validate_secret_envs("prod", {"DEEPTUTOR_ATTEMPT_REF_SECRET": "x" * 32})

    assert ok is True
    assert messages == ["DEEPTUTOR_ATTEMPT_REF_SECRET=set fingerprint=680cb4c5"]


def test_cli_missing_prod_secret_exits_nonzero(monkeypatch) -> None:
    monkeypatch.delenv("DEEPTUTOR_ATTEMPT_REF_SECRET", raising=False)

    assert main(["--env", "prod"]) == 1
