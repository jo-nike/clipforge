"""
Resilience utilities for ClipForge - retry logic and circuit breaker patterns
Provides decorators and classes for handling transient failures gracefully
"""

import asyncio
import functools
import secrets
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, List, Optional, Type

from core.exceptions import ExternalServiceError, MediaProcessingError, PlexConnectionError
from core.logging import get_logger

logger = get_logger("resilience")


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class RetryStrategy:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on: Optional[List[Type[Exception]]] = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on = retry_on or [Exception]

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if we should retry based on exception type and attempt count"""
        if attempt >= self.max_attempts:
            return False

        return any(isinstance(exception, exc_type) for exc_type in self.retry_on)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay before next attempt"""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add jitter to prevent thundering herd
            delay *= 0.5 + secrets.randbelow(1000) / 1000.0

        return delay


class CircuitBreaker:
    """Circuit breaker implementation for external service calls"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED

        self.logger = get_logger(f"circuit_breaker.{self.__class__.__name__}")

    def _reset(self) -> None:
        """Reset circuit breaker to closed state"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.logger.info("Circuit breaker reset to CLOSED state")

    def _record_success(self) -> None:
        """Record successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.logger.info("Circuit breaker test call succeeded, resetting to CLOSED")
            self._reset()

    def _record_failure(self) -> None:
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.warning(
                f"Circuit breaker tripped to OPEN state after {self.failure_count} failures"
            )

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit breaker"""
        if self.state != CircuitState.OPEN:
            return True

        if self.last_failure_time is None:
            return True

        time_since_failure = datetime.now() - self.last_failure_time
        if time_since_failure.total_seconds() >= self.recovery_timeout:
            self.state = CircuitState.HALF_OPEN
            self.logger.info("Circuit breaker entering HALF_OPEN state for testing")
            return True

        return False

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection"""
        if not self._should_attempt_reset():
            raise ExternalServiceError(
                f"Circuit breaker is OPEN - service unavailable for {self.recovery_timeout}s"
            )

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exception:
            self._record_failure()
            raise
        except Exception as e:
            # Unexpected exception, don't count as failure
            self.logger.warning(f"Unexpected exception in circuit breaker: {e}")
            raise

    async def call_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute async function with circuit breaker protection"""
        if not self._should_attempt_reset():
            raise ExternalServiceError(
                f"Circuit breaker is OPEN - service unavailable for {self.recovery_timeout}s"
            )

        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exception:
            self._record_failure()
            raise
        except Exception as e:
            # Unexpected exception, don't count as failure
            self.logger.warning(f"Unexpected exception in circuit breaker: {e}")
            raise


def retry_on_failure(strategy: Optional[RetryStrategy] = None) -> Callable:
    """Decorator to add retry logic to functions"""
    if strategy is None:
        strategy = RetryStrategy()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(strategy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if not strategy.should_retry(e, attempt + 1):
                        logger.warning(
                            f"Not retrying {func.__name__} after attempt {attempt + 1}: {type(e).__name__}: {e}"
                        )
                        break

                    if attempt + 1 < strategy.max_attempts:
                        delay = strategy.get_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{strategy.max_attempts} for {func.__name__} "
                            f"after {delay:.2f}s due to: {type(e).__name__}: {e}"
                        )
                        time.sleep(delay)

            # Re-raise the last exception
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected error in retry logic")

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(strategy.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if not strategy.should_retry(e, attempt + 1):
                        logger.warning(
                            f"Not retrying {func.__name__} after attempt {attempt + 1}: {type(e).__name__}: {e}"
                        )
                        break

                    if attempt + 1 < strategy.max_attempts:
                        delay = strategy.get_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{strategy.max_attempts} for {func.__name__} "
                            f"after {delay:.2f}s due to: {type(e).__name__}: {e}"
                        )
                        await asyncio.sleep(delay)

            # Re-raise the last exception
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected error in retry logic")

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Predefined retry strategies for common use cases
PLEX_API_RETRY = RetryStrategy(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    exponential_base=2.0,
    retry_on=[PlexConnectionError, ExternalServiceError],
)

FFMPEG_RETRY = RetryStrategy(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    exponential_base=2.0,
    retry_on=[MediaProcessingError],
)

DATABASE_RETRY = RetryStrategy(
    max_attempts=3,
    base_delay=0.1,
    max_delay=1.0,
    exponential_base=2.0,
    retry_on=[Exception],  # Database connection errors vary by driver
)

# Predefined circuit breakers
PLEX_CIRCUIT_BREAKER = CircuitBreaker(
    failure_threshold=5, recovery_timeout=30, expected_exception=PlexConnectionError
)

FFMPEG_CIRCUIT_BREAKER = CircuitBreaker(
    failure_threshold=3, recovery_timeout=60, expected_exception=MediaProcessingError
)


def with_retry(strategy: Optional[RetryStrategy] = None) -> Callable:
    """Simple retry decorator with default strategy"""
    return retry_on_failure(strategy or RetryStrategy())


def with_plex_retry() -> Callable:
    """Retry decorator specifically for Plex API calls"""
    return retry_on_failure(PLEX_API_RETRY)


def with_ffmpeg_retry() -> Callable:
    """Retry decorator specifically for FFmpeg operations"""
    return retry_on_failure(FFMPEG_RETRY)


# Utility functions for manual retry logic
async def retry_async(
    func: Callable, *args: Any, strategy: Optional[RetryStrategy] = None, **kwargs: Any
) -> Any:
    """Manual async retry logic for when decorators can't be used"""
    if strategy is None:
        strategy = RetryStrategy()

    last_exception = None

    for attempt in range(strategy.max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if not strategy.should_retry(e, attempt + 1):
                break

            if attempt + 1 < strategy.max_attempts:
                delay = strategy.get_delay(attempt)
                await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error in retry logic")


def retry_sync(
    func: Callable, *args: Any, strategy: Optional[RetryStrategy] = None, **kwargs: Any
) -> Any:
    """Manual sync retry logic for when decorators can't be used"""
    if strategy is None:
        strategy = RetryStrategy()

    last_exception = None

    for attempt in range(strategy.max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if not strategy.should_retry(e, attempt + 1):
                break

            if attempt + 1 < strategy.max_attempts:
                delay = strategy.get_delay(attempt)
                time.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected error in retry logic")
