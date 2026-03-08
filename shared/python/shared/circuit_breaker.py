"""Circuit breaker wrapper using pybreaker."""

import pybreaker

from shared.exceptions import CircuitOpenError
from shared.logging import get_logger

logger = get_logger("circuit_breaker")


class ServiceCircuitBreaker:
    """Circuit breaker for inter-service calls.

    States:
        CLOSED: Normal operation, requests pass through.
        OPEN: Failures exceeded threshold, requests fail fast.
        HALF_OPEN: Testing if service recovered, limited requests.
    """

    def __init__(
        self,
        service_name: str,
        fail_max: int = 3,
        reset_timeout: int = 30,
        exclude: list[type] | None = None,
    ):
        """Initialize circuit breaker.

        Args:
            service_name: Target service name.
            fail_max: Number of failures before opening circuit.
            reset_timeout: Seconds before trying half-open.
            exclude: Exception types that should not count as failures.
        """
        self.service_name = service_name
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            exclude=exclude or [],
            listeners=[_CircuitBreakerListener(service_name)],
            name=service_name,
        )

    @property
    def state(self) -> str:
        """Current circuit breaker state."""
        return self._breaker.current_state

    def call(self, func, *args, **kwargs):
        """Execute a function through the circuit breaker.

        Args:
            func: Callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Result of func.

        Raises:
            CircuitOpenError: If circuit is open.
        """
        try:
            return self._breaker.call(func, *args, **kwargs)
        except pybreaker.CircuitBreakerError:
            raise CircuitOpenError(self.service_name)

    async def call_async(self, func, *args, **kwargs):
        """Execute an async function through the circuit breaker.

        Args:
            func: Async callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Result of func.

        Raises:
            CircuitOpenError: If circuit is open.
        """
        try:
            return await self._breaker.call_async(func, *args, **kwargs)
        except pybreaker.CircuitBreakerError:
            raise CircuitOpenError(self.service_name)


class _CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Logs circuit breaker state transitions."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    def state_change(self, cb, old_state, new_state):
        logger.warning(
            "circuit_breaker_state_change",
            service=self.service_name,
            old_state=old_state.name,
            new_state=new_state.name,
        )

    def failure(self, cb, exc):
        logger.warning(
            "circuit_breaker_failure",
            service=self.service_name,
            error=str(exc),
            failure_count=cb.fail_counter,
        )

    def success(self, cb):
        logger.debug(
            "circuit_breaker_success",
            service=self.service_name,
        )
