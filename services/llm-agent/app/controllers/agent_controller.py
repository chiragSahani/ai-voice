"""gRPC servicer implementing the LLMAgent service RPCs."""

import json
import time
from typing import Any

import grpc

from shared.logging import get_logger

from app.config import LLMAgentConfig
from app.services.safety_filter import SafetyFilter
from app.services.streaming_service import StreamingService
from app.services.llm_service import LLMService
from app.validators.agent_validator import ChatValidator

logger = get_logger("agent_controller")


class LLMAgentServicer:
    """gRPC servicer for the LLMAgent service.

    Implements:
        - Chat: server-streaming RPC returning token-by-token response chunks.
        - Summarize: unary RPC returning conversation summary.
    """

    def __init__(
        self,
        config: LLMAgentConfig,
        streaming_service: StreamingService,
        llm_service: LLMService,
        safety_filter: SafetyFilter,
        validator: ChatValidator,
    ):
        self._config = config
        self._streaming_service = streaming_service
        self._llm_service = llm_service
        self._safety_filter = safety_filter
        self._validator = validator

    async def Chat(self, request, context):
        """Handle a Chat RPC: receive ChatRequest, stream ChatResponseChunk.

        The proto defines: rpc Chat (ChatRequest) returns (stream ChatResponseChunk)

        Args:
            request: ChatRequest protobuf message.
            context: gRPC service context.

        Yields:
            ChatResponseChunk protobuf messages.
        """
        start_time = time.monotonic()
        session_id = request.session_id

        # Validate request
        validation_error = self._validator.validate_chat_request(request)
        if validation_error:
            logger.warning(
                "chat_validation_failed",
                session_id=session_id,
                error=validation_error,
            )
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, validation_error)
            return

        logger.info(
            "chat_request_received",
            session_id=session_id,
            language=request.language,
            history_turns=len(request.history),
            has_patient_context=bool(request.patient_context),
        )

        # Safety check on user input
        input_safety = self._safety_filter.check_input(request.transcript)
        if input_safety.severity == "critical":
            logger.warning(
                "emergency_input_detected",
                session_id=session_id,
            )
            # Continue processing but the system prompt will guide emergency handling

        # Convert proto history to dict list
        history = _proto_history_to_dicts(request.history)

        # Convert patient_context map to dict
        patient_context = dict(request.patient_context) if request.patient_context else None
        patient_id = patient_context.get("patient_id") if patient_context else None

        # Import proto message types for building responses
        from generated import llm_agent_pb2

        try:
            async for chunk in self._streaming_service.stream_response(
                transcript=request.transcript,
                history=history,
                session_id=session_id,
                patient_context=patient_context,
                language=request.language or "en",
                tools_enabled=True,
                system_prompt_override=request.system_prompt_override or None,
                patient_id=patient_id,
            ):
                # Convert internal model to proto message
                proto_chunk = llm_agent_pb2.ChatResponseChunk(
                    session_id=session_id,
                    text_delta=chunk.text,
                    is_final=chunk.is_final,
                    finish_reason=chunk.finish_reason or "",
                )

                # Add tool call if present
                if chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        proto_chunk.tool_call.CopyFrom(
                            llm_agent_pb2.ToolCall(
                                id=f"call_{tc.tool_name}",
                                name=tc.tool_name,
                                arguments_json=json.dumps(tc.arguments),
                            )
                        )

                # Add metadata on final chunk
                if chunk.is_final:
                    total_ms = int((time.monotonic() - start_time) * 1000)
                    proto_chunk.metadata.CopyFrom(
                        llm_agent_pb2.ResponseMetadata(
                            model_used=chunk.model_used or "",
                            prompt_tokens=chunk.prompt_tokens or 0,
                            completion_tokens=chunk.completion_tokens or 0,
                            total_tokens=(chunk.prompt_tokens or 0) + (chunk.completion_tokens or 0),
                            latency_ms=total_ms,
                            used_fallback=chunk.used_fallback,
                        )
                    )

                yield proto_chunk

        except Exception as err:
            logger.error(
                "chat_stream_error",
                session_id=session_id,
                error=str(err),
                exc_info=True,
            )
            # Yield error chunk
            error_chunk = llm_agent_pb2.ChatResponseChunk(
                session_id=session_id,
                text_delta="I'm sorry, an error occurred. Please try again.",
                is_final=True,
                finish_reason="error",
            )
            yield error_chunk

    async def Summarize(self, request, context):
        """Handle a Summarize RPC: receive SummarizeRequest, return SummarizeResponse.

        Args:
            request: SummarizeRequest protobuf message.
            context: gRPC service context.

        Returns:
            SummarizeResponse protobuf message.
        """
        session_id = request.session_id

        # Validate
        validation_error = self._validator.validate_summarize_request(request)
        if validation_error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, validation_error)
            return

        logger.info(
            "summarize_request_received",
            session_id=session_id,
            turns=len(request.turns),
        )

        # Convert proto turns to message dicts
        messages = []
        for turn in request.turns:
            messages.append({
                "role": turn.role,
                "content": turn.content,
            })

        from generated import llm_agent_pb2

        try:
            result = await self._llm_service.summarize(
                messages=messages,
                session_id=session_id,
                language=request.language or "en",
            )

            return llm_agent_pb2.SummarizeResponse(
                session_id=session_id,
                summary=result["summary"],
                key_entities=result["key_entities"],
                sentiment=result["sentiment"],
                actions_taken=result["actions_taken"],
            )

        except Exception as err:
            logger.error(
                "summarize_error",
                session_id=session_id,
                error=str(err),
                exc_info=True,
            )
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Summarization failed: {str(err)}",
            )


def _proto_history_to_dicts(history) -> list[dict[str, Any]]:
    """Convert proto ConversationTurn repeated field to a list of dicts.

    Args:
        history: Repeated ConversationTurn proto messages.

    Returns:
        List of message dicts with role, content, and optional tool metadata.
    """
    result = []
    for turn in history:
        msg: dict[str, Any] = {
            "role": turn.role,
            "content": turn.content,
        }
        if turn.tool_call_id:
            msg["tool_call_id"] = turn.tool_call_id
        if turn.tool_call and turn.tool_call.name:
            msg["tool_calls"] = [{
                "id": turn.tool_call.id,
                "type": "function",
                "function": {
                    "name": turn.tool_call.name,
                    "arguments": turn.tool_call.arguments_json,
                },
            }]
            msg["content"] = turn.content or None
        result.append(msg)
    return result
