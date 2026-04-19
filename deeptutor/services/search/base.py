"""Base search provider with shared retries and circuit breaking."""

from abc import ABC, abstractmethod
import logging
import os
from typing import Any

import requests
import tenacity
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from deeptutor.logging import get_logger
from deeptutor.services.config import get_env_store
from deeptutor.utils.error_rate_tracker import record_provider_call
from deeptutor.utils.network.circuit_breaker import (
    is_call_allowed,
    record_call_failure,
    record_call_success,
)

from .exceptions import (
    SearchAPIError,
    SearchCircuitBreakerError,
    SearchError,
    SearchRateLimitError,
    SearchTimeoutError,
)
from .types import WebSearchResponse

# Unified API key environment variable
SEARCH_API_KEY_ENV = "SEARCH_API_KEY"
MAX_RETRY_DELAY_SECONDS = 30.0
BASE_RETRY_DELAY_SECONDS = 1.0


class BaseSearchProvider(ABC):
    """Abstract base class for search providers.

    All providers use a unified SEARCH_API_KEY environment variable.
    Each provider has its own BASE_URL defined as a class constant.
    """

    name: str = "base"
    display_name: str = "Base Provider"
    description: str = ""
    requires_api_key: bool = True
    supports_answer: bool = False  # Whether provider generates LLM answers
    BASE_URL: str = ""  # Each provider defines its own endpoint
    API_KEY_ENV_VARS: tuple[str, ...] = (SEARCH_API_KEY_ENV,)

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        """
        Initialize the provider.

        Args:
            api_key: API key for the provider. If not provided, will be read from SEARCH_API_KEY.
            **kwargs: Additional configuration options.
        """
        self.logger = get_logger(f"Search.{self.__class__.__name__}", level="INFO")
        self.api_key = api_key or self._get_api_key()
        self.config = kwargs
        self.proxy = kwargs.get("proxy")

    def _get_api_key(self) -> str:
        """Get API key from provider-specific env vars with SEARCH_API_KEY fallback."""
        key = ""
        for env_name in self.API_KEY_ENV_VARS:
            key = get_env_store().get(env_name, "") or os.getenv(env_name, "")
            if key:
                break
        if self.requires_api_key and not key:
            raise ValueError(
                f"{self.name} requires one of {self.API_KEY_ENV_VARS}. "
                f"Please set it before using this provider."
            )
        return key

    @abstractmethod
    def search(self, query: str, **kwargs: Any) -> WebSearchResponse:
        """
        Execute search and return standardized response.

        Args:
            query: The search query.
            **kwargs: Provider-specific options.

        Returns:
            WebSearchResponse: Standardized search response.
        """
        pass

    def _check_circuit_breaker(self) -> None:
        if not is_call_allowed(self.name):
            record_provider_call(self.name, success=False)
            raise SearchCircuitBreakerError(
                f"Circuit breaker open for provider {self.name}",
                provider=self.name,
            )

    def _should_record_failure(self, error: SearchError) -> bool:
        if isinstance(error, (SearchTimeoutError, SearchRateLimitError)):
            return True
        if isinstance(error, SearchAPIError):
            if error.status_code is None:
                return True
            return error.status_code >= 500
        return False

    def _should_retry_error(self, error: BaseException) -> bool:
        if isinstance(error, (SearchTimeoutError, SearchRateLimitError)):
            return True
        if isinstance(error, SearchAPIError):
            return bool(error.retryable)
        return False

    def _wait_strategy(self, retry_state: tenacity.RetryCallState) -> float:
        outcome = retry_state.outcome
        if outcome is None:
            return BASE_RETRY_DELAY_SECONDS
        exc = outcome.exception()
        if isinstance(exc, SearchRateLimitError) and exc.retry_after is not None:
            return max(0.0, min(float(exc.retry_after), MAX_RETRY_DELAY_SECONDS))
        wait_fn = tenacity.wait_exponential(
            multiplier=1.5,
            min=BASE_RETRY_DELAY_SECONDS,
            max=MAX_RETRY_DELAY_SECONDS,
        )
        return float(wait_fn(retry_state))

    def _map_request_exception(self, exc: Exception) -> SearchError:
        if isinstance(exc, SearchError):
            return exc
        if isinstance(exc, requests.Timeout):
            return SearchTimeoutError(f"{self.name} request timed out", provider=self.name)
        if isinstance(exc, requests.HTTPError):
            response = exc.response
            status_code = response.status_code if response is not None else None
            body = ""
            if response is not None:
                try:
                    body = response.text
                except Exception:
                    body = ""
            retry_after: float | None = None
            if response is not None:
                header_value = response.headers.get("Retry-After")
                if header_value:
                    try:
                        retry_after = float(header_value)
                    except (TypeError, ValueError):
                        retry_after = None
            message = f"{self.name} API error"
            if status_code is not None:
                message += f" ({status_code})"
            if body:
                message += f": {body}"
            if status_code == 429:
                return SearchRateLimitError(
                    message,
                    provider=self.name,
                    retry_after=retry_after,
                    status_code=status_code,
                )
            return SearchAPIError(
                message,
                provider=self.name,
                status_code=status_code,
                retryable=status_code is None or status_code >= 500,
            )
        if isinstance(exc, requests.RequestException):
            return SearchAPIError(
                f"{self.name} request failed: {exc}",
                provider=self.name,
                retryable=True,
            )
        return SearchError(f"{self.name} search failed: {exc}", provider=self.name)

    def _execute(self, fn, *args: Any, **kwargs: Any) -> Any:
        self._check_circuit_breaker()
        try:
            result = fn(*args, **kwargs)
            record_provider_call(self.name, success=True)
            record_call_success(self.name)
            return result
        except Exception as exc:
            mapped = self._map_request_exception(exc)
            record_provider_call(self.name, success=False)
            if self._should_record_failure(mapped):
                record_call_failure(self.name)
            raise mapped from exc

    def execute_with_retry(
        self,
        fn,
        *args: Any,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(max_retries + 1),
            wait=self._wait_strategy,
            retry=retry_if_exception(self._should_retry_error),
            reraise=True,
            before_sleep=tenacity.before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        )
        for attempt in retrying:
            with attempt:
                return self._execute(fn, *args, **kwargs)
        raise RuntimeError("Retry loop exited without returning")

    def request_json(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> Any:
        def _send() -> Any:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise SearchAPIError(
                    f"{self.name} returned invalid JSON",
                    provider=self.name,
                    retryable=False,
                ) from exc

        return self.execute_with_retry(_send, max_retries=max_retries)

    def is_available(self) -> bool:
        """
        Check if provider is available (dependencies installed, API key set).

        Returns:
            bool: True if provider is available, False otherwise.
        """
        try:
            if self.requires_api_key:
                key = self.api_key or get_env_store().get(SEARCH_API_KEY_ENV, "")
                if not key:
                    return False
            return True
        except (ValueError, ImportError):
            return False


__all__ = ["BaseSearchProvider", "SEARCH_API_KEY_ENV"]
