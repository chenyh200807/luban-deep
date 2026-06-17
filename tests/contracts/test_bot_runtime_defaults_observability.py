"""G7 — unknown bot_id must surface an observable warning, not resolve silently.

A non-empty bot_id that is not in BOT_RUNTIME_DEFAULTS falls back to the default
capability engine instead of the intended tutorbot_runtime. The resolver emits a
WARNING so that silent fallback is observable (bot_id is request data; this is the
only place an unregistered value becomes visible). The return contract is unchanged.
"""

from __future__ import annotations

import logging

from deeptutor.contracts.bot_runtime_defaults import resolve_bot_runtime_defaults


def test_known_bot_id_resolves_without_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        result = resolve_bot_runtime_defaults(bot_id="construction-exam-coach")
    assert result is not None
    assert result.execution_engine == "tutorbot_runtime"
    assert "unknown bot_id" not in caplog.text


def test_unknown_bot_id_warns_and_returns_none(caplog) -> None:
    # construction-exam-tutor is a supabase_kb_alias, NOT a registered bot_id.
    with caplog.at_level(logging.WARNING):
        result = resolve_bot_runtime_defaults(bot_id="construction-exam-tutor")
    assert result is None  # contract unchanged: still None for unknown
    assert "unknown bot_id" in caplog.text
    assert "construction-exam-tutor" in caplog.text


def test_empty_bot_id_no_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        result = resolve_bot_runtime_defaults(bot_id="")
    assert result is None
    assert "unknown bot_id" not in caplog.text
