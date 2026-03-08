"""Streaming coordination service for tool-call-aware response generation."""

import json
from typing import Any, AsyncGenerator, Optional

from shared.logging import get_logger

from app.config import LLMAgentConfig
from app.models.responses import ChatResponseChunk, ToolCallResult
from app.models.tool_definitions import TOOL_DEFINITIONS, TOOLS_REQUIRING_PATIENT_ID
from app.services.llm_service import LLMService
from app.services.prompt_builder import build_messages_for_llm

logger = get_logger("streaming_service")


class StreamingService:
    """Coordinates streaming LLM responses with tool call dispatch.

    When the LLM requests a tool call, this service:
    1. Pauses text generation
    2. Dispatches the tool call to the tool orchestrator
    3. Feeds the result back into the LLM
    4. Resumes streaming the response
    """

    def __init__(
        self,
        config: LLMAgentConfig,
        llm_service: LLMService,
        tool_executor: Any,  # ToolOrchestratorClient
    ):
        self._config = config
        self._llm_service = llm_service
        self._tool_executor = tool_executor

    async def stream_response(
        self,
        transcript: str,
        history: list[dict[str, Any]],
        session_id: str,
        patient_context: Optional[dict[str, str]] = None,
        language: str = "en",
        tools_enabled: bool = True,
        system_prompt_override: Optional[str] = None,
        patient_id: Optional[str] = None,
        max_tool_rounds: int = 3,
    ) -> AsyncGenerator[ChatResponseChunk, None]:
        """Stream a complete response, handling tool calls automatically.

        Args:
            transcript: Current user utterance.
            history: Conversation history.
            session_id: Session identifier.
            patient_context: Patient info for personalization.
            language: Response language.
            tools_enabled: Whether tools are available.
            system_prompt_override: Custom system prompt override.
            patient_id: Identified patient ID (for tool authorization).
            max_tool_rounds: Max consecutive tool call rounds before forcing text.

        Yields:
            ChatResponseChunk objects (text deltas, tool results, final chunk).
        """
        # Build initial messages
        messages = build_messages_for_llm(
            transcript=transcript,
            history=history,
            patient_context=patient_context,
            language=language,
            tools_enabled=tools_enabled,
            system_prompt_override=system_prompt_override,
            max_history_turns=self._config.max_history_turns,
        )

        # Select tools
        tools = TOOL_DEFINITIONS if tools_enabled else None

        tool_round = 0

        while tool_round < max_tool_rounds:
            tool_round += 1
            accumulated_text = ""
            final_chunk: Optional[ChatResponseChunk] = None

            # Stream from LLM
            async for chunk in self._llm_service.stream_chat(
                messages=messages,
                session_id=session_id,
                tools=tools,
                tool_choice="auto" if tools else "none",
            ):
                if chunk.is_final:
                    final_chunk = chunk
                else:
                    accumulated_text += chunk.text
                    yield chunk

            if final_chunk is None:
                # Shouldn't happen, but guard
                yield ChatResponseChunk(
                    session_id=session_id,
                    is_final=True,
                    finish_reason="error",
                )
                return

            # If no tool calls, we're done
            if final_chunk.finish_reason != "tool_calls" or not final_chunk.tool_calls:
                yield final_chunk
                return

            # Process tool calls
            logger.info(
                "processing_tool_calls",
                session_id=session_id,
                tool_round=tool_round,
                tool_count=len(final_chunk.tool_calls),
                tools=[tc.tool_name for tc in final_chunk.tool_calls],
            )

            # Check patient_id requirement
            executed_tool_calls: list[ToolCallResult] = []
            for tc in final_chunk.tool_calls:
                if tc.tool_name in TOOLS_REQUIRING_PATIENT_ID and not patient_id:
                    # Cannot execute -- patient not identified
                    executed_tool_calls.append(ToolCallResult(
                        tool_name=tc.tool_name,
                        arguments=tc.arguments,
                        result=None,
                        success=False,
                        error="Patient must be identified before using this tool. Use lookup_patient first.",
                    ))
                else:
                    # Execute via tool orchestrator
                    result = await self._execute_tool(
                        session_id=session_id,
                        tool_name=tc.tool_name,
                        arguments=tc.arguments,
                        patient_id=patient_id,
                    )
                    executed_tool_calls.append(result)

            # Yield tool results to caller (for visibility)
            yield ChatResponseChunk(
                session_id=session_id,
                text="",
                is_final=False,
                tool_calls=executed_tool_calls,
                finish_reason="tool_calls",
                model_used=final_chunk.model_used,
                used_fallback=final_chunk.used_fallback,
            )

            # Inject tool results back into messages for next LLM round
            tool_messages = self._llm_service.get_accumulated_tool_calls_as_messages(
                executed_tool_calls
            )
            messages.extend(tool_messages)

            # Continue loop to let LLM respond with tool results in context

        # If we exhausted tool rounds, force a final text response without tools
        logger.warning(
            "max_tool_rounds_reached",
            session_id=session_id,
            max_rounds=max_tool_rounds,
        )

        async for chunk in self._llm_service.stream_chat(
            messages=messages,
            session_id=session_id,
            tools=None,
            tool_choice="none",
        ):
            yield chunk

    async def _execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        patient_id: Optional[str] = None,
    ) -> ToolCallResult:
        """Execute a single tool call via the tool orchestrator.

        Args:
            session_id: Session ID.
            tool_name: Tool name to execute.
            arguments: Tool arguments.
            patient_id: Patient ID for authorization.

        Returns:
            ToolCallResult with execution outcome.
        """
        try:
            result = await self._tool_executor.execute_tool(
                session_id=session_id,
                tool_name=tool_name,
                arguments_json=json.dumps(arguments),
                patient_id=patient_id or "",
            )

            if result.success:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=json.loads(result.result_json) if result.result_json else {},
                    success=True,
                )
            else:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=None,
                    success=False,
                    error=result.error_message or "Tool execution failed",
                )

        except Exception as err:
            logger.error(
                "tool_execution_error",
                session_id=session_id,
                tool_name=tool_name,
                error=str(err),
            )
            return ToolCallResult(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                success=False,
                error=f"Tool execution error: {str(err)}",
            )
