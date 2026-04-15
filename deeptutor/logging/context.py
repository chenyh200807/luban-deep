from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4

_CONTEXT_FIELDS = ("request_id", "user_id", "session_id", "turn_id")
_CONTEXT_VARS: dict[str, ContextVar[str]] = {
    field: ContextVar(f"deeptutor_{field}", default="")
    for field in _CONTEXT_FIELDS
}


def generate_request_id() -> str:
    """Generate a new request id for request-bound logging context."""
    return uuid4().hex


def bind_log_context(**fields: str | None) -> dict[str, Token[str]]:
    """Bind one or more logging context fields and return reset tokens."""
    tokens: dict[str, Token[str]] = {}
    for field, value in fields.items():
        if field not in _CONTEXT_VARS:
            continue
        normalized = str(value or "").strip()
        tokens[field] = _CONTEXT_VARS[field].set(normalized)
    return tokens


def reset_log_context(tokens: dict[str, Token[str]]) -> None:
    """Restore previously bound logging context fields."""
    for field, token in tokens.items():
        context_var = _CONTEXT_VARS.get(field)
        if context_var is None:
            continue
        context_var.reset(token)


def get_log_context() -> dict[str, str]:
    """Return the current logging context payload."""
    return {field: context_var.get() for field, context_var in _CONTEXT_VARS.items()}


def bind_request_id(request_id: str | None = None) -> tuple[str, dict[str, Token[str]]]:
    """Backward-compatible request-id binder that delegates to log context."""
    normalized = str(request_id or "").strip() or generate_request_id()
    return normalized, bind_log_context(request_id=normalized)


def get_request_id() -> str:
    """Return the current request id, or an empty string outside request scope."""
    return _CONTEXT_VARS["request_id"].get()


def reset_request_id(token: dict[str, Token[str]]) -> None:
    """Backward-compatible request-id reset wrapper."""
    reset_log_context(token)
