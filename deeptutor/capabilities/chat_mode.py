"""Shared helpers for chat fast/deep mode defaults."""

from __future__ import annotations

import os
from typing import Literal


def get_default_chat_mode() -> Literal["fast", "deep", "smart"]:
    raw = str(
        os.getenv("CHAT_DEFAULT_MODE")
        or os.getenv("NEXT_PUBLIC_CHAT_DEFAULT_MODE")
        or "deep"
    ).strip().lower()
    if raw == "fast":
        return "fast"
    if raw == "smart":
        return "smart"
    return "deep"
