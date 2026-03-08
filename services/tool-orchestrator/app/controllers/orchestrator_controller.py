"""gRPC servicer implementing the ToolOrchestrator service."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import grpc

from shared.logging import get_logger

from app.models.requests import BatchToolRequest, ToolRequest
from app.models.responses import ToolInfo

logger = get_logger("grpc_controller")

if TYPE_CHECKING:
    from app.services.orchestrator_service import ExecutionService
    from app.services.tool_registry import ToolRegistry

# The generated protobuf modules are imported at runtime.
# We use string-based attribute access to avoid hard import failures
# when proto stubs are not yet compiled in the dev environment.
try:
    from shared.proto import tool_orchestrator_pb2, tool_orchestrator_pb2_grpc

    _PROTO_AVAILABLE = True
except ImportError:
    _PROTO_AVAILABLE = False
    tool_orchestrator_pb2 = None  # type: ignore[assignment]
    tool_orchestrator_pb2_grpc = None  # type: ignore[assignment]


class ToolOrchestratorServicer:
    """gRPC servicer for the ToolOrchestrator service.

    Implements:
        - ExecuteTool (unary)
        - ExecuteToolBatch (unary)
        - ListTools (unary)
    """

    def __init__(
        self,
        execution_service: "ExecutionService",
        registry: "ToolRegistry",
    ) -> None:
        self._execution_service = execution_service
        self._registry = registry

    # ---- ExecuteTool (unary) ----

    async def ExecuteTool(self, request, context):  # noqa: N802
        """Execute a single tool call.

        Args:
            request: ToolRequest proto message.
            context: gRPC service context.

        Returns:
            ToolResponse proto message.
        """
        start = time.monotonic()
        try:
            # Parse arguments JSON
            arguments = _parse_json(request.arguments_json)

            tool_request = ToolRequest(
                tool_name=request.tool_name,
                arguments=arguments,
                session_id=request.session_id,
                correlation_id=request.correlation_id,
                patient_id=request.patient_id,
            )

            result = await self._execution_service.execute_tool(tool_request)

            return _build_tool_response_proto(result)

        except json.JSONDecodeError as exc:
            logger.warning("invalid_arguments_json", error=str(exc))
            return _error_response_proto(
                correlation_id=request.correlation_id,
                error_message=f"Invalid arguments JSON: {exc}",
                error_code="INVALID_JSON",
                latency_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            logger.exception("execute_tool_error", error=str(exc))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return _error_response_proto(
                correlation_id=getattr(request, "correlation_id", ""),
                error_message=f"Internal server error: {exc}",
                error_code="INTERNAL_ERROR",
                latency_ms=_elapsed_ms(start),
            )

    # ---- ExecuteToolBatch (unary) ----

    async def ExecuteToolBatch(self, request, context):  # noqa: N802
        """Execute multiple tool calls in parallel.

        Args:
            request: ToolBatchRequest proto message.
            context: gRPC service context.

        Returns:
            ToolBatchResponse proto message.
        """
        start = time.monotonic()
        try:
            tool_requests: list[ToolRequest] = []
            for proto_req in request.requests:
                arguments = _parse_json(proto_req.arguments_json)
                tool_requests.append(
                    ToolRequest(
                        tool_name=proto_req.tool_name,
                        arguments=arguments,
                        session_id=proto_req.session_id or request.session_id,
                        correlation_id=proto_req.correlation_id,
                        patient_id=proto_req.patient_id,
                    )
                )

            batch_request = BatchToolRequest(
                session_id=request.session_id,
                requests=tool_requests,
            )

            batch_result = await self._execution_service.execute_batch(batch_request)

            proto_responses = [
                _build_tool_response_proto(r) for r in batch_result.responses
            ]

            if not _PROTO_AVAILABLE:
                return {"responses": proto_responses, "total_latency_ms": batch_result.total_execution_time_ms}

            return tool_orchestrator_pb2.ToolBatchResponse(
                responses=proto_responses,
                total_latency_ms=batch_result.total_execution_time_ms,
            )

        except Exception as exc:
            logger.exception("execute_tool_batch_error", error=str(exc))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            if not _PROTO_AVAILABLE:
                return {"responses": [], "total_latency_ms": _elapsed_ms(start)}
            return tool_orchestrator_pb2.ToolBatchResponse(
                responses=[],
                total_latency_ms=_elapsed_ms(start),
            )

    # ---- ListTools (unary) ----

    async def ListTools(self, request, context):  # noqa: N802
        """List all available tools and their schemas.

        Args:
            request: ListToolsRequest proto message.
            context: gRPC service context.

        Returns:
            ListToolsResponse proto message.
        """
        try:
            tools: list[ToolInfo] = self._registry.list_tools()

            if not _PROTO_AVAILABLE:
                return {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters_json_schema": json.dumps(t.parameters_schema),
                            "requires_patient_id": t.requires_patient_id,
                            "required_permissions": t.required_permissions,
                        }
                        for t in tools
                    ]
                }

            proto_tools = []
            for t in tools:
                proto_tools.append(
                    tool_orchestrator_pb2.ToolDefinition(
                        name=t.name,
                        description=t.description,
                        parameters_json_schema=json.dumps(t.parameters_schema),
                        requires_patient_id=t.requires_patient_id,
                        required_permissions=t.required_permissions,
                    )
                )

            return tool_orchestrator_pb2.ListToolsResponse(tools=proto_tools)

        except Exception as exc:
            logger.exception("list_tools_error", error=str(exc))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            if not _PROTO_AVAILABLE:
                return {"tools": []}
            return tool_orchestrator_pb2.ListToolsResponse(tools=[])


# ---------- Helper functions ----------


def _parse_json(raw: str) -> dict:
    """Parse a JSON string, returning an empty dict for empty/missing input."""
    if not raw or not raw.strip():
        return {}
    return json.loads(raw)


def _build_tool_response_proto(result):
    """Convert an internal ToolResponse to a proto ToolResponse."""
    from app.models.responses import ToolResponse as InternalToolResponse

    if not _PROTO_AVAILABLE:
        return {
            "correlation_id": result.correlation_id,
            "success": result.success,
            "result_json": json.dumps(result.result) if result.result else "",
            "error_message": result.error_message,
            "error_code": result.error_code,
            "latency_ms": result.execution_time_ms,
        }

    return tool_orchestrator_pb2.ToolResponse(
        correlation_id=result.correlation_id,
        success=result.success,
        result_json=json.dumps(result.result) if result.result else "",
        error_message=result.error_message,
        error_code=result.error_code,
        latency_ms=result.execution_time_ms,
    )


def _error_response_proto(
    correlation_id: str,
    error_message: str,
    error_code: str,
    latency_ms: int,
):
    """Build an error ToolResponse proto."""
    if not _PROTO_AVAILABLE:
        return {
            "correlation_id": correlation_id,
            "success": False,
            "result_json": "",
            "error_message": error_message,
            "error_code": error_code,
            "latency_ms": latency_ms,
        }

    return tool_orchestrator_pb2.ToolResponse(
        correlation_id=correlation_id,
        success=False,
        result_json="",
        error_message=error_message,
        error_code=error_code,
        latency_ms=latency_ms,
    )


def _elapsed_ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)
