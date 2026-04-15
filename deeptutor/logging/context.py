from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4

_request_id: ContextVar[str] = ContextVar("deeptutor_request_id", default="")


def generate_request_id() -> str:
    """Generate a new request id for HTTP-bound logging context."""
    return uuid4().hex


def bind_request_id(request_id: str | None = None) -> tuple[str, Token[str]]:
    """Bind a request id for the current context and return it with the reset token."""
    normalized = (request_id or "").strip() or generate_request_id()
    return normalized, _request_id.set(normalized)


def get_request_id() -> str:
    """Return the current request id, or an empty string outside request scope."""
    return _request_id.get()


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request id context."""
    _request_id.reset(token)
