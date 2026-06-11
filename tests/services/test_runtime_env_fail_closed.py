"""Fail-closed invariants for production-environment detection.

Regression guard for the pre-launch root cause: "authorized for dev
capabilities" was encoded as the inverse of a fuzzy production check that
defaulted fail-OPEN, so an unset / misspelled DEEPTUTOR_ENV silently opened
every dev backdoor (dev login, demo tokens, fallback signing secrets).

The suite installs an *empty* env store (no on-disk ``.env``, no fallbacks) and
clears the runtime-env keys from ``os.environ`` so "unset" can be simulated
deterministically regardless of the developer's local ``.env``.
"""

from __future__ import annotations

import importlib

import pytest

from deeptutor.services import runtime_env
from deeptutor.services.config import env_store as env_store_mod
from deeptutor.services.config.env_store import EnvStore

_ALL_ENV_KEYS = (
    "DEEPTUTOR_ENV",
    "DEEPTUTOR_RUNTIME_ENV",
    "APP_ENV",
    "ENV",
    "ENVIRONMENT",
    "SERVICE_ENV",
    "ALIYUN_DEPLOY_ENV",
)


@pytest.fixture(autouse=True)
def _isolated_empty_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point the env store at a non-existent file and clear runtime-env keys.

    This removes the influence of the developer's real ``.env`` (which may carry
    e.g. ``SERVICE_ENV=development``) so each test controls the environment
    purely through ``monkeypatch.setenv``.
    """

    for key in _ALL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    store = EnvStore(path=tmp_path / "missing.env", fallback_paths=())
    monkeypatch.setattr(env_store_mod, "get_env_store", lambda: store)


def test_unset_environment_is_production() -> None:
    assert runtime_env.runtime_environment(default="") == ""
    assert runtime_env.is_production_environment() is True


def test_misspelled_environment_is_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "prouction")
    assert runtime_env.is_production_environment() is True


def test_staging_is_treated_as_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "staging")
    assert runtime_env.is_production_environment() is True


def test_aliyun_is_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "aliyun")
    assert runtime_env.is_production_environment() is True


@pytest.mark.parametrize("value", ["local", "dev", "development", "test", "ci", "eval"])
def test_explicit_non_production_values_disable_safeguards(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", value)
    assert runtime_env.is_production_environment() is False


@pytest.mark.parametrize("value", ["prod", "production"])
def test_explicit_production_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", value)
    assert runtime_env.is_production_environment() is True


def test_attempt_refs_requires_secret_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # attempt_refs must inherit the shared fail-closed authority: an unset
    # environment with no configured secret must refuse the dev fallback.
    monkeypatch.delenv("DEEPTUTOR_ATTEMPT_REF_SECRET", raising=False)
    attempt_refs = importlib.import_module(
        "deeptutor.services.learner_state.attempt_refs"
    )
    with pytest.raises(RuntimeError):
        attempt_refs._secret()


def test_attempt_refs_uses_shared_authority_via_app_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Proves the drifted second definition is gone: setting only APP_ENV
    # (which the old private _is_prod_runtime ignored) now drives attempt_refs.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_ATTEMPT_REF_SECRET", raising=False)
    attempt_refs = importlib.import_module(
        "deeptutor.services.learner_state.attempt_refs"
    )
    with pytest.raises(RuntimeError):
        attempt_refs._secret()
