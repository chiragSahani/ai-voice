"""gRPC client for the Tool Orchestrator service."""

import json
from typing import Optional

from shared.circuit_breaker import ServiceCircuitBreaker
from shared.grpc_utils import create_grpc_channel
from shared.logging import get_logger

from app.config import LLMAgentConfig

logger = get_logger("tool_orchestrator_client")


class ToolOrchestratorClient:
    """gRPC client for calling the Tool Orchestrator service.

    Wraps calls with circuit breaker and timeout handling.
    """

    def __init__(self, config: LLMAgentConfig):
        self._config = config
        self._target = f"{config.tool_orchestrator_host}:{config.tool_orchestrator_port}"
        self._timeout_s = config.tool_orchestrator_timeout_ms / 1000.0
        self._channel = None
        self._stub = None
        self._breaker = ServiceCircuitBreaker(
            service_name="tool-orchestrator",
            fail_max=config.circuit_breaker_fail_max,
            reset_timeout=config.circuit_breaker_reset_timeout,
        )

    async def connect(self) -> None:
        """Establish gRPC channel to the tool orchestrator."""
        self._channel = create_grpc_channel(
            target=self._target,
            timeout_ms=self._config.tool_orchestrator_timeout_ms,
        )
        # Import generated stubs
        from generated import tool_orchestrator_pb2_grpc

        self._stub = tool_orchestrator_pb2_grpc.ToolOrchestratorStub(self._channel)
        logger.info("tool_orchestrator_connected", target=self._target)

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            logger.info("tool_orchestrator_disconnected")

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments_json: str,
        patient_id: str = "",
        correlation_id: str = "",
    ):
        """Execute a tool call via the Tool Orchestrator service.

        Args:
            session_id: Session identifier.
            tool_name: Name of the tool to execute.
            arguments_json: JSON-encoded tool arguments.
            patient_id: Patient ID for authorization.
            correlation_id: Correlation ID linking to LLM tool_call.id.

        Returns:
            ToolResponse protobuf message with success, result_json, error_message.

        Raises:
            Exception: If circuit breaker is open or call fails.
        """
        from generated import tool_orchestrator_pb2

        request = tool_orchestrator_pb2.ToolRequest(
            session_id=session_id,
            tool_name=tool_name,
            arguments_json=arguments_json,
            correlation_id=correlation_id,
            patient_id=patient_id,
        )

        logger.info(
            "executing_tool",
            session_id=session_id,
            tool_name=tool_name,
            patient_id=patient_id,
        )

        async def _call():
            return await self._stub.ExecuteTool(
                request,
                timeout=self._timeout_s,
            )

        response = await self._breaker.call_async(_call)

        logger.info(
            "tool_executed",
            session_id=session_id,
            tool_name=tool_name,
            success=response.success,
            latency_ms=response.latency_ms,
        )

        return response

    async def execute_tool_batch(
        self,
        session_id: str,
        tool_calls: list[dict],
        patient_id: str = "",
    ):
        """Execute multiple tool calls in parallel via the Tool Orchestrator.

        Args:
            session_id: Session identifier.
            tool_calls: List of dicts with tool_name, arguments_json, correlation_id.
            patient_id: Patient ID for authorization.

        Returns:
            ToolBatchResponse protobuf message.
        """
        from generated import tool_orchestrator_pb2

        requests = []
        for tc in tool_calls:
            requests.append(tool_orchestrator_pb2.ToolRequest(
                session_id=session_id,
                tool_name=tc["tool_name"],
                arguments_json=tc.get("arguments_json", "{}"),
                correlation_id=tc.get("correlation_id", ""),
                patient_id=patient_id,
            ))

        batch_request = tool_orchestrator_pb2.ToolBatchRequest(
            session_id=session_id,
            requests=requests,
        )

        async def _call():
            return await self._stub.ExecuteToolBatch(
                batch_request,
                timeout=self._timeout_s,
            )

        response = await self._breaker.call_async(_call)

        logger.info(
            "tool_batch_executed",
            session_id=session_id,
            tool_count=len(tool_calls),
            total_latency_ms=response.total_latency_ms,
        )

        return response

    @property
    def circuit_state(self) -> str:
        """Current circuit breaker state."""
        return self._breaker.state
