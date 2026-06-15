"""Traffic control primitives for LLM providers."""

from __future__ import annotations

import asyncio
import os
import time
from types import TracebackType
from typing import Any

from deeptutor.logging import get_logger

logger = get_logger(__name__)
_PROVIDER_TRAFFIC_CONTROLLERS: dict[tuple[int, str, int, int, float], "TrafficController"] = {}


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _env_float(name: str, default: float) -> float:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.1, value)


def get_provider_traffic_controller(
    *,
    provider_name: str,
    config: Any | None = None,
) -> "TrafficController":
    """Return the process-local provider bulkhead for both factory and TutorBot providers."""
    configured_concurrency = int(getattr(config, "max_concurrency", 20) or 20)
    configured_rpm = int(getattr(config, "requests_per_minute", 600) or 600)
    max_concurrency = _env_int("DEEPTUTOR_LLM_MAX_CONCURRENCY", configured_concurrency)
    rpm = _env_int("DEEPTUTOR_LLM_REQUESTS_PER_MINUTE", configured_rpm)
    timeout = _env_float("DEEPTUTOR_LLM_ACQUIRE_TIMEOUT_SECONDS", 30.0)
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    key = (loop_id, provider_name or "unknown", max_concurrency, rpm, timeout)
    controller = _PROVIDER_TRAFFIC_CONTROLLERS.get(key)
    if controller is None:
        controller = TrafficController(
            provider_name=provider_name or "unknown",
            max_concurrency=max_concurrency,
            requests_per_minute=rpm,
            acquisition_timeout=timeout,
        )
        _PROVIDER_TRAFFIC_CONTROLLERS[key] = controller
    return controller


class TrafficController:
    """
    Controls concurrency and rate limits for LLM providers.

    Protects both the local system (resource exhaustion) and
    remote provider (rate limits).
    """

    def __init__(
        self,
        provider_name: str,
        max_concurrency: int = 20,
        requests_per_minute: int = 600,
        acquisition_timeout: float = 30.0,
    ) -> None:
        """
        Args:
            provider_name: Label for logging.
            max_concurrency: Max simultaneous in-flight requests (bulkheads).
            requests_per_minute: Max RPM allowed before local throttling.
            acquisition_timeout: Max seconds to wait for a slot before failing.
        """
        self.provider_name = provider_name
        self.max_concurrency = max_concurrency
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be > 0")
        self.rpm = requests_per_minute
        self.acquisition_timeout = acquisition_timeout

        # Concurrency Gate
        self._semaphore = asyncio.Semaphore(max_concurrency)

        # Rate Limiting (Token Bucket)
        self._tokens = float(requests_per_minute)
        self._last_refill = time.monotonic()
        self._fill_rate = requests_per_minute / 60.0  # tokens per second
        self._lock = asyncio.Lock()  # Protects token state

    async def _wait_for_token(self) -> None:
        """Consumes a rate limit token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill

            # Refill tokens
            new_tokens = elapsed * self._fill_rate
            if new_tokens > 0:
                self._tokens = min(float(self.rpm), self._tokens + new_tokens)
                self._last_refill = now

            # Consume token
            if self._tokens >= 1:
                self._tokens -= 1.0
                return

            # Calculate wait time needed for 1 token
            wait_time = (1.0 - self._tokens) / self._fill_rate

        # Wait outside lock to avoid blocking other tasks
        if wait_time > 0:
            logger.debug("[%s] Rate limit active, waiting %.2fs" % (self.provider_name, wait_time))
            await asyncio.sleep(wait_time)
            # Recursively try again (simplest way to ensure thread safety after sleep)
            await self._wait_for_token()

    async def __aenter__(self) -> TrafficController:
        """
        Acquire concurrency slot AND rate limit token.
        Raises asyncio.TimeoutError if system is overloaded.
        """
        start = time.monotonic()

        # 1. Acquire Concurrency Slot
        try:
            # wait_for adds a timeout to the semaphore acquisition
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.acquisition_timeout)
        except TimeoutError:
            logger.error(
                "[%s] Local concurrency limit (%s) exceeded for >%.1fs."
                % (self.provider_name, self.max_concurrency, self.acquisition_timeout)
            )
            raise

        # 2. Acquire Rate Limit Token (if we passed concurrency check)
        # Note: We do this AFTER semaphore to ensure we don't wait for tokens
        # while holding a concurrency slot if we don't have to,
        # BUT strictly speaking, holding the semaphore while waiting for rate limits
        # prevents queue jumping.
        try:
            await self._wait_for_token()
        except BaseException:
            # If rate limiter fails/cancels, release semaphore
            self._semaphore.release()
            raise

        wait_duration = time.monotonic() - start
        if wait_duration > 1.0:
            logger.warning("[%s] Traffic control wait: %.2fs" % (self.provider_name, wait_duration))

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release concurrency slot."""
        self._semaphore.release()
        return None


__all__ = ["TrafficController", "get_provider_traffic_controller"]
