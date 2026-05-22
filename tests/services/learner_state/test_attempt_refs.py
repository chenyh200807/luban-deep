from __future__ import annotations

import importlib

import pytest


def test_attempt_ref_round_trips_without_exposing_event_id() -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref, verify_attempt_ref

    token = sign_attempt_ref(user_id="u1", event_id="evt_secret", question_id="q1")

    assert "evt_secret" not in token
    payload = verify_attempt_ref(token, user_id="u1")
    assert payload == {"event_id": "evt_secret", "question_id": "q1"}


def test_attempt_ref_rejects_wrong_user() -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref, verify_attempt_ref

    token = sign_attempt_ref(user_id="u1", event_id="evt_secret", question_id="q1")

    assert verify_attempt_ref(token, user_id="u2") is None


def test_attempt_ref_rejects_empty_user_or_event() -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    with pytest.raises(ValueError):
        sign_attempt_ref(user_id="", event_id="evt_secret")
    with pytest.raises(ValueError):
        sign_attempt_ref(user_id="u1", event_id="")


def test_verify_rejects_empty_user_even_with_valid_token() -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref, verify_attempt_ref

    token = sign_attempt_ref(user_id="u1", event_id="evt1")

    assert verify_attempt_ref(token, user_id="") is None


def test_unknown_kid_rejected() -> None:
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref, verify_attempt_ref

    token = sign_attempt_ref(user_id="u1", event_id="evt1")
    tampered = "x" + token[1:]

    assert verify_attempt_ref(tampered, user_id="u1") is None
    assert verify_attempt_ref("not.a.valid.token", user_id="u1") is None


def test_prod_runtime_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    import deeptutor.services.learner_state.attempt_refs as mod

    monkeypatch.setenv("DEEPTUTOR_ENV", "prod")
    monkeypatch.delenv("DEEPTUTOR_ATTEMPT_REF_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        importlib.reload(mod)

    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    importlib.reload(mod)
