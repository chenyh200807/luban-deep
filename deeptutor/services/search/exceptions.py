"""Typed search provider errors."""

from __future__ import annotations


class SearchError(Exception):
    """Base typed error for web-search provider failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class SearchAPIError(SearchError):
    """HTTP or upstream API error from a search provider."""


class SearchTimeoutError(SearchAPIError):
    """Timeout while calling a search provider."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=True)


class SearchRateLimitError(SearchAPIError):
    """Rate-limited search provider response."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retry_after: float | None = None,
        status_code: int | None = 429,
    ) -> None:
        super().__init__(message, provider=provider, status_code=status_code, retryable=True)
        self.retry_after = retry_after


class SearchCircuitBreakerError(SearchError):
    """Search provider call blocked by the circuit breaker."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=False)

