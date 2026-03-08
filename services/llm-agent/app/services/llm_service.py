"""Core LLM inference service using litellm for unified model access."""

import json
import time
from typing import Any, AsyncGenerator, Optional

import litellm

from shared.circuit_breaker import ServiceCircuitBreaker
from shared.logging import get_logger

from app.config import LLMAgentConfig
from app.models.responses import ChatResponseChunk, ToolCallResult
from app.services.safety_filter import SafetyFilter

logger = get_logger("llm_service")


class LLMService:
    """Handles LLM inference with streaming, fallback, and tool calling."""

    def __init__(self, config: LLMAgentConfig, safety_filter: SafetyFilter):
        self._config = config
        self._safety_filter = safety_filter
        self._primary_breaker = ServiceCircuitBreaker(
            service_name=f"llm-{config.primary_model}",
            fail_max=config.circuit_breaker_fail_max,
            reset_timeout=config.circuit_breaker_reset_timeout,
        )
        self._fallback_breaker = ServiceCircuitBreaker(
            service_name=f"llm-{config.fallback_model}",
            fail_max=config.circuit_breaker_fail_max,
            reset_timeout=config.circuit_breaker_reset_timeout,
        )
        # Disable litellm's own logging noise
        litellm.set_verbose = False

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        session_id: str,
        tools: Optional[list[dict]] = None,
        tool_choice: str = "auto",
    ) -> AsyncGenerator[ChatResponseChunk, None]:
        """Stream chat completion tokens from the LLM.

        Tries the primary model first, falls back to the secondary on failure.
        Yields ChatResponseChunk objects for each token delta.

        Args:
            messages: OpenAI-format messages list.
            session_id: Session identifier for tracking.
            tools: OpenAI function-calling tool definitions.
            tool_choice: Tool choice mode: auto, none, required.

        Yields:
            ChatResponseChunk for each streamed delta.
        """
        used_fallback = False
        model = self._config.primary_model
        breaker = self._primary_breaker

        try:
            async for chunk in self._stream_with_model(
                model=model,
                messages=messages,
                session_id=session_id,
                tools=tools,
                tool_choice=tool_choice,
                breaker=breaker,
                used_fallback=False,
            ):
                yield chunk
            return
        except Exception as primary_err:
            logger.warning(
                "primary_model_failed",
                model=model,
                error=str(primary_err),
                session_id=session_id,
            )
            if not self._config.enable_fallback:
                yield ChatResponseChunk(
                    session_id=session_id,
                    text="I'm sorry, I'm experiencing technical difficulties. Please try again.",
                    is_final=True,
                    finish_reason="error",
                )
                return

        # Fallback to secondary model
        used_fallback = True
        model = self._config.fallback_model
        breaker = self._fallback_breaker

        try:
            async for chunk in self._stream_with_model(
                model=model,
                messages=messages,
                session_id=session_id,
                tools=tools,
                tool_choice=tool_choice,
                breaker=breaker,
                used_fallback=True,
            ):
                yield chunk
        except Exception as fallback_err:
            logger.error(
                "fallback_model_failed",
                model=model,
                error=str(fallback_err),
                session_id=session_id,
            )
            yield ChatResponseChunk(
                session_id=session_id,
                text="I'm sorry, I'm experiencing technical difficulties. Please try again shortly.",
                is_final=True,
                finish_reason="error",
            )

    async def _stream_with_model(
        self,
        model: str,
        messages: list[dict[str, Any]],
        session_id: str,
        tools: Optional[list[dict]],
        tool_choice: str,
        breaker: ServiceCircuitBreaker,
        used_fallback: bool,
    ) -> AsyncGenerator[ChatResponseChunk, None]:
        """Stream from a specific model through a circuit breaker.

        Args:
            model: Model identifier (e.g. gpt-4o, claude-3-5-sonnet-20241022).
            messages: Conversation messages.
            session_id: Session ID.
            tools: Tool definitions.
            tool_choice: Tool choice mode.
            breaker: Circuit breaker for this model.
            used_fallback: Whether this is the fallback model.

        Yields:
            ChatResponseChunk per delta.
        """
        start_time = time.monotonic()
        ttft_logged = False
        accumulated_tool_calls: dict[int, dict[str, Any]] = {}
        prompt_tokens = 0
        completion_tokens = 0

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "top_p": self._config.top_p,
            "frequency_penalty": self._config.frequency_penalty,
            "presence_penalty": self._config.presence_penalty,
            "stream": True,
            "timeout": self._config.llm_timeout_ms / 1000.0,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await breaker.call_async(litellm.acompletion, **kwargs)

        async for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            # Track TTFT
            if not ttft_logged and (delta.content or delta.tool_calls):
                ttft_ms = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "llm_ttft",
                    model=model,
                    ttft_ms=ttft_ms,
                    session_id=session_id,
                )
                ttft_logged = True

            # Accumulate tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        accumulated_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        accumulated_tool_calls[idx]["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        accumulated_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            # Yield text deltas
            text_delta = delta.content or ""
            if text_delta:
                # Apply safety filter on each delta
                safety_result = self._safety_filter.check_output(text_delta)
                if safety_result.is_safe:
                    yield ChatResponseChunk(
                        session_id=session_id,
                        text=text_delta,
                        is_final=False,
                        model_used=model,
                        used_fallback=used_fallback,
                    )
                else:
                    filtered = safety_result.filtered_text or ""
                    if filtered:
                        yield ChatResponseChunk(
                            session_id=session_id,
                            text=filtered,
                            is_final=False,
                            model_used=model,
                            used_fallback=used_fallback,
                        )

            # Check for finish
            if choice.finish_reason:
                # Extract usage from the final chunk if available
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0

                # Build tool call results for final chunk
                tool_call_results = []
                if accumulated_tool_calls:
                    for _idx, tc_data in sorted(accumulated_tool_calls.items()):
                        try:
                            args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                        except json.JSONDecodeError:
                            args = {"_raw": tc_data["arguments"]}
                        tool_call_results.append(
                            ToolCallResult(
                                tool_name=tc_data["name"],
                                arguments=args,
                            )
                        )

                total_ms = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "llm_completion_done",
                    model=model,
                    session_id=session_id,
                    finish_reason=choice.finish_reason,
                    total_ms=total_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    tool_calls_count=len(tool_call_results),
                    used_fallback=used_fallback,
                )

                yield ChatResponseChunk(
                    session_id=session_id,
                    text="",
                    is_final=True,
                    tool_calls=tool_call_results,
                    finish_reason=choice.finish_reason,
                    model_used=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    used_fallback=used_fallback,
                )

    async def summarize(
        self,
        messages: list[dict[str, Any]],
        session_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Generate a conversation summary (non-streaming).

        Args:
            messages: Conversation messages to summarize.
            session_id: Session ID.
            language: Language of the summary.

        Returns:
            Parsed summary dict with keys: summary, key_entities, sentiment, actions_taken.
        """
        summary_prompt = self._build_summary_prompt(messages, language)

        try:
            response = await self._primary_breaker.call_async(
                litellm.acompletion,
                model=self._config.summary_model,
                messages=summary_prompt,
                temperature=0.1,
                max_tokens=self._config.summary_max_tokens,
                timeout=self._config.llm_timeout_ms / 1000.0,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            logger.info(
                "summarization_complete",
                session_id=session_id,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
            )

            return {
                "summary": result.get("summary", ""),
                "key_entities": result.get("key_entities", []),
                "sentiment": result.get("sentiment", "neutral"),
                "actions_taken": result.get("actions_taken", []),
            }

        except Exception as err:
            logger.error(
                "summarization_failed",
                session_id=session_id,
                error=str(err),
            )
            return {
                "summary": "Summary generation failed.",
                "key_entities": [],
                "sentiment": "neutral",
                "actions_taken": [],
            }

    def _build_summary_prompt(
        self, messages: list[dict[str, Any]], language: str
    ) -> list[dict[str, str]]:
        """Build the prompt for conversation summarization.

        Args:
            messages: Conversation turns.
            language: Target summary language.

        Returns:
            Messages list for the summarization LLM call.
        """
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
            for m in messages
            if m.get("content")
        )

        system = (
            "You are a clinical conversation summarizer. Analyze the following conversation "
            "between a patient and an AI appointment assistant. Respond ONLY with a JSON object "
            "containing these fields:\n"
            '- "summary": A concise 2-3 sentence summary of the conversation.\n'
            '- "key_entities": Array of extracted entities (doctor names, dates, departments, '
            "medical terms mentioned).\n"
            '- "sentiment": The patient\'s overall sentiment: "positive", "neutral", or "negative".\n'
            '- "actions_taken": Array of actions that were performed (e.g., "booked_appointment", '
            '"checked_availability", "cancelled_appointment", "rescheduled_appointment", '
            '"looked_up_patient").\n'
            "Do NOT include any PHI (protected health information) like full names or phone numbers "
            "in the summary. Use initials or generic references instead.\n"
        )

        if language != "en":
            system += f"\nWrite the summary in the same language as the conversation ({language})."

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Conversation:\n{conversation_text}"},
        ]

    def get_accumulated_tool_calls_as_messages(
        self, tool_calls: list[ToolCallResult]
    ) -> list[dict[str, Any]]:
        """Convert accumulated tool calls into assistant message format for re-injection.

        Args:
            tool_calls: List of tool call results.

        Returns:
            List of messages to append to conversation (assistant + tool results).
        """
        if not tool_calls:
            return []

        # Build the assistant message with tool_calls
        openai_tool_calls = []
        for i, tc in enumerate(tool_calls):
            openai_tool_calls.append({
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments),
                },
            })

        messages: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": openai_tool_calls,
            }
        ]

        # Add tool result messages
        for i, tc in enumerate(tool_calls):
            result_content = json.dumps(tc.result) if tc.result else json.dumps({"error": tc.error or "Unknown error"})
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": result_content,
            })

        return messages
