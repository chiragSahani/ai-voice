"""Execution service - the core engine that runs tools."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from shared.exceptions import CircuitOpenError, ServiceUnavailableError
from shared.logging import get_logger

from app.clients.http_client import AppointmentSchedulerClient, PatientMemoryClient
from app.config import get_config
from app.models.domain import ToolExecutionContext
from app.models.requests import BatchToolRequest, ToolRequest
from app.models.responses import BatchToolResponse, ToolResponse
from app.services.tool_registry import ToolRegistry
from app.validators.tool_validator import ToolValidator

logger = get_logger("execution_service")

# Prometheus-style counters (using shared metrics module if available)
_tool_executions: dict[str, dict[str, int]] = {}


class ExecutionService:
    """Executes tool requests, handling timeouts, errors, and metrics."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._validator = ToolValidator(registry)
        self._config = get_config()

        # Downstream HTTP clients (shared across executions)
        self._appointment_client = AppointmentSchedulerClient()
        self._patient_client = PatientMemoryClient()

    async def close(self) -> None:
        """Shut down HTTP clients gracefully."""
        await self._appointment_client.close()
        await self._patient_client.close()

    # ---------- Single tool execution ----------

    async def execute_tool(self, request: ToolRequest) -> ToolResponse:
        """Execute a single tool request.

        Args:
            request: The tool request to execute.

        Returns:
            ToolResponse with the result or error details.
        """
        start = time.monotonic()

        # Validate
        validation_errors = self._validator.validate_request(request)
        if validation_errors:
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message="; ".join(validation_errors),
                error_code="VALIDATION_ERROR",
                execution_time_ms=_elapsed_ms(start),
            )

        tool = self._registry.get_tool(request.tool_name)
        if tool is None:
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message=f"Unknown tool: {request.tool_name}",
                error_code="UNKNOWN_TOOL",
                execution_time_ms=_elapsed_ms(start),
            )

        context = ToolExecutionContext(
            session_id=request.session_id,
            correlation_id=request.correlation_id,
            patient_id=request.patient_id,
        )

        # Determine which downstream client to inject
        client: Any
        if request.tool_name == "lookup_patient":
            client = self._patient_client
        else:
            client = self._appointment_client

        try:
            result = await asyncio.wait_for(
                tool.handler(context, client, **request.arguments),
                timeout=self._config.tool_execution_timeout,
            )

            elapsed = _elapsed_ms(start)
            self._record_metric(request.tool_name, success=True, elapsed_ms=elapsed)

            logger.info(
                "tool_executed",
                tool=request.tool_name,
                session_id=request.session_id,
                correlation_id=request.correlation_id,
                duration_ms=elapsed,
            )

            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=True,
                result=result,
                execution_time_ms=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = _elapsed_ms(start)
            self._record_metric(request.tool_name, success=False, elapsed_ms=elapsed)
            logger.error(
                "tool_timeout",
                tool=request.tool_name,
                session_id=request.session_id,
                timeout_s=self._config.tool_execution_timeout,
            )
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message=(
                    f"Tool execution timed out after "
                    f"{self._config.tool_execution_timeout}s"
                ),
                error_code="TIMEOUT",
                execution_time_ms=elapsed,
            )

        except CircuitOpenError as exc:
            elapsed = _elapsed_ms(start)
            self._record_metric(request.tool_name, success=False, elapsed_ms=elapsed)
            logger.warning(
                "tool_circuit_open",
                tool=request.tool_name,
                downstream=exc.service_name,
            )
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message=str(exc),
                error_code="CIRCUIT_OPEN",
                execution_time_ms=elapsed,
            )

        except ServiceUnavailableError as exc:
            elapsed = _elapsed_ms(start)
            self._record_metric(request.tool_name, success=False, elapsed_ms=elapsed)
            logger.error(
                "tool_service_unavailable",
                tool=request.tool_name,
                downstream=exc.service_name,
            )
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message=str(exc),
                error_code="SERVICE_UNAVAILABLE",
                execution_time_ms=elapsed,
            )

        except Exception as exc:
            elapsed = _elapsed_ms(start)
            self._record_metric(request.tool_name, success=False, elapsed_ms=elapsed)
            logger.exception(
                "tool_execution_error",
                tool=request.tool_name,
                session_id=request.session_id,
                error=str(exc),
            )
            return ToolResponse(
                tool_name=request.tool_name,
                correlation_id=request.correlation_id,
                success=False,
                error_message=f"Internal error: {exc}",
                error_code="INTERNAL_ERROR",
                execution_time_ms=elapsed,
            )

    # ---------- Batch tool execution ----------

    async def execute_batch(self, batch: BatchToolRequest) -> BatchToolResponse:
        """Execute multiple tool requests concurrently.

        Args:
            batch: Batch containing a list of tool requests.

        Returns:
            BatchToolResponse with individual results and total latency.
        """
        start = time.monotonic()
        max_concurrent = self._config.batch_max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_with_semaphore(req: ToolRequest) -> ToolResponse:
            async with semaphore:
                return await self.execute_tool(req)

        responses = await asyncio.gather(
            *[_run_with_semaphore(req) for req in batch.requests],
            return_exceptions=False,
        )

        total_ms = _elapsed_ms(start)
        logger.info(
            "batch_executed",
            session_id=batch.session_id,
            total_tools=len(batch.requests),
            total_ms=total_ms,
        )

        return BatchToolResponse(
            responses=list(responses),
            total_execution_time_ms=total_ms,
        )

    # ---------- Metrics ----------

    @staticmethod
    def _record_metric(tool_name: str, *, success: bool, elapsed_ms: int) -> None:
        """Record tool execution metrics (in-process counters)."""
        if tool_name not in _tool_executions:
            _tool_executions[tool_name] = {"success": 0, "failure": 0, "total_ms": 0}
        bucket = _tool_executions[tool_name]
        if success:
            bucket["success"] += 1
        else:
            bucket["failure"] += 1
        bucket["total_ms"] += elapsed_ms

    @staticmethod
    def get_metrics() -> dict[str, dict[str, int]]:
        """Return aggregated per-tool execution metrics."""
        return dict(_tool_executions)


def _elapsed_ms(start: float) -> int:
    """Milliseconds elapsed since *start* (monotonic)."""
    return round((time.monotonic() - start) * 1000)
