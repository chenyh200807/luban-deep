from __future__ import annotations

import pytest

from deeptutor.capabilities.request_contracts import validate_capability_config


def test_chat_config_strips_runtime_client_turn_id() -> None:
    config = validate_capability_config(
        "chat",
        {
            "chat_mode": "smart",
            "client_turn_id": "tb_surface_turn_1",
        },
    )

    assert config == {"chat_mode": "smart", "auto_tools": True, "bot_id": ""}


def test_chat_config_still_rejects_unknown_public_keys() -> None:
    with pytest.raises(ValueError, match="unknown_key"):
        validate_capability_config("chat", {"unknown_key": "still-forbidden"})
