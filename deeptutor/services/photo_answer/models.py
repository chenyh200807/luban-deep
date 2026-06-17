"""Constants, status machine and errors for the photo-answer input layer.

Budget caps are plan §3.3 authority values: soft cap bounds the automatic
routing spend; the hard cap is only reachable through the single
user-triggered re-recognition escalation per session.
"""

from __future__ import annotations

# 1 元 = 1_000_000 micros — cents cannot express sub-cent per-page prices
# like 0.0074 元 (Codex C1).
SOFT_CAP_MICROS = 100_000  # 0.10 元/题：自动路由预算
HARD_CAP_MICROS = 300_000  # 0.30 元/题：含用户主动重识别
DEFAULT_DAILY_SESSION_LIMIT = 20

SESSION_STATUSES = (
    "created",
    "pages_uploaded",
    "processing",
    "awaiting_confirm",
    "confirmed",
    "submitted",
    "failed",
)

# Explicit transition table (plan §6). "failed" is reachable from any
# non-terminal state; retry routes failed back to processing.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"pages_uploaded", "failed"},
    "pages_uploaded": {"pages_uploaded", "processing", "failed"},
    "processing": {"awaiting_confirm", "failed"},
    "awaiting_confirm": {"confirmed", "processing", "failed"},
    "confirmed": {"submitted", "failed"},
    "submitted": set(),
    "failed": {"processing"},
}


class PhotoAnswerError(Exception):
    """Base error for the photo-answer layer."""


class InvalidTransition(PhotoAnswerError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Invalid session transition: {current} -> {target}")
        self.current = current
        self.target = target


class DailyQuotaExceeded(PhotoAnswerError):
    """Per-user/day session quota guard (anti-abuse, plan §3.3 ④)."""


def assert_transition(current: str, target: str) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(current, target)
