"""Voice pipeline orchestrator — the latency-critical core of audio-gateway.

Processes a single voice turn through the full pipeline:
    Audio chunks -> STT -> LLM Agent -> TTS -> Audio response

Key design decisions for minimal latency:
    1. All stages are concurrent via asyncio — no stage waits for the
       previous stage to fully complete before starting.
    2. STT streams partial transcripts; we wait only for the final one.
    3. LLM response tokens are buffered to sentence boundaries, then
       immediately forwarded to TTS (pipeline parallelism).
    4. TTS audio chunks are yielded as soon as available.
    5. Metrics are collected per-stage for latency profiling.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, AsyncIterator

from shared.logging import get_logger

from app.clients.grpc_clients import grpc_pool
from app.clients.session_client import session_client
from app.config import settings
from app.models.domain import PipelineMetrics, PipelineStatus
from app.models.responses import TranscriptMessage
from app.services.audio_processor import compute_audio_duration_ms, prepare_for_client, prepare_for_stt

logger = get_logger("pipeline")

# Regex for sentence-boundary splitting (split on . ! ? followed by space or end)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u0964\u0965])\s+")

# Minimum text length before we flush to TTS (avoids tiny TTS calls)
_MIN_FLUSH_CHARS = 20


class VoicePipeline:
    """Orchestrates a single voice turn through STT -> LLM -> TTS."""

    def __init__(self, session_id: str, language: str = "en") -> None:
        self.session_id = session_id
        self.language = language
        self.metrics = PipelineMetrics()
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the pipeline (e.g., user interrupted)."""
        self._cancelled = True

    async def process_turn(
        self,
        audio_chunks: AsyncIterator[bytes],
        conversation_history: list[dict] | None = None,
        patient_context: dict[str, str] | None = None,
        on_transcript: Any | None = None,
    ) -> AsyncIterator[bytes]:
        """Run the full voice pipeline for one conversational turn.

        Args:
            audio_chunks: Async iterator yielding raw PCM16 audio from client.
            conversation_history: Previous turns for LLM context.
            patient_context: Patient data for personalization.
            on_transcript: Optional async callback(TranscriptMessage) for
                           sending partial/final transcripts to the client.

        Yields:
            PCM16 audio bytes for playback to the client.
        """
        self.metrics.turn_start = time.monotonic()

        # ---- Stage 1: STT ----
        stt_stage = self.metrics.add_stage("stt")
        stt_stage.start()

        final_transcript = ""
        detected_language = self.language

        async def _preprocessed_audio() -> AsyncIterator[bytes]:
            """Pre-process audio chunks before sending to STT."""
            async for raw_chunk in audio_chunks:
                if self._cancelled:
                    return
                processed = prepare_for_stt(raw_chunk)
                yield processed

        try:
            async for event in grpc_pool.stt.streaming_recognize(
                audio_chunks=_preprocessed_audio(),
                session_id=self.session_id,
                language_hint=self.language,
                sample_rate=settings.audio_sample_rate,
            ):
                if self._cancelled:
                    break

                text = event.get("text", "")
                is_final = event.get("is_final", False)
                lang = event.get("language", self.language)
                confidence = event.get("transcript_confidence", 0.0)

                # Send transcript events to the client in real-time
                if on_transcript and text:
                    transcript_msg = TranscriptMessage(
                        text=text,
                        is_final=is_final,
                        language=lang,
                        confidence=confidence,
                    )
                    await on_transcript(transcript_msg)

                if is_final and text:
                    final_transcript = text
                    detected_language = lang
                    stt_stage.complete()

        except Exception as exc:
            stt_stage.fail()
            logger.error(
                "stt_stage_failed",
                error=str(exc),
                session_id=self.session_id,
            )
            raise

        if not final_transcript:
            logger.debug("stt_no_transcript", session_id=self.session_id)
            return

        logger.info(
            "stt_final_transcript",
            text=final_transcript[:100],
            language=detected_language,
            duration_ms=round(stt_stage.duration_ms, 1),
            session_id=self.session_id,
        )

        # Store user turn asynchronously (don't block pipeline)
        asyncio.create_task(
            self._store_turn("user", final_transcript, detected_language)
        )

        if self._cancelled:
            return

        # ---- Stage 2 + 3: LLM -> TTS (pipelined) ----
        # LLM tokens are buffered to sentence boundaries and streamed to TTS
        # concurrently. TTS audio is yielded as it becomes available.

        llm_stage = self.metrics.add_stage("llm")
        tts_stage = self.metrics.add_stage("tts")

        # Channel for sentence-boundary text chunks from LLM -> TTS
        text_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=32)

        # Channel for audio chunks from TTS -> client
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)

        full_response_text: list[str] = []

        async def _llm_to_sentences() -> None:
            """Stream LLM response and split into sentence chunks for TTS."""
            llm_stage.start()
            buffer = ""
            try:
                async for chunk in grpc_pool.llm.chat(
                    session_id=self.session_id,
                    transcript=final_transcript,
                    language=detected_language,
                    history=conversation_history,
                    patient_context=patient_context,
                ):
                    if self._cancelled:
                        break

                    text_delta = chunk.get("text_delta", "")
                    if not text_delta:
                        continue

                    buffer += text_delta

                    # Split on sentence boundaries
                    parts = _SENTENCE_BOUNDARY.split(buffer)
                    if len(parts) > 1:
                        # All parts except the last are complete sentences
                        for sentence in parts[:-1]:
                            sentence = sentence.strip()
                            if sentence and len(sentence) >= _MIN_FLUSH_CHARS:
                                full_response_text.append(sentence)
                                await text_queue.put(sentence)
                        buffer = parts[-1]

                # Flush remaining buffer
                remainder = buffer.strip()
                if remainder:
                    full_response_text.append(remainder)
                    await text_queue.put(remainder)

                llm_stage.complete()

            except Exception as exc:
                llm_stage.fail()
                logger.error(
                    "llm_stage_failed",
                    error=str(exc),
                    session_id=self.session_id,
                )
            finally:
                await text_queue.put(None)  # Sentinel

        async def _tts_producer() -> None:
            """Read sentence chunks and stream them through TTS."""
            tts_stage.start()
            first_audio = True

            async def _text_chunk_iter() -> AsyncIterator[str]:
                while True:
                    chunk = await text_queue.get()
                    if chunk is None:
                        return
                    yield chunk

            try:
                async for audio_bytes in grpc_pool.tts.streaming_synthesize(
                    text_chunks=_text_chunk_iter(),
                    session_id=self.session_id,
                    language=detected_language,
                ):
                    if self._cancelled:
                        break

                    # Convert TTS output sample rate to client sample rate
                    client_audio = prepare_for_client(
                        audio_bytes,
                        tts_sample_rate=settings.tts_output_sample_rate,
                        client_sample_rate=settings.audio_sample_rate,
                    )

                    if first_audio:
                        first_audio = False
                        self.metrics.first_audio_out = time.monotonic()

                    await audio_queue.put(client_audio)

                tts_stage.complete()

            except Exception as exc:
                tts_stage.fail()
                logger.error(
                    "tts_stage_failed",
                    error=str(exc),
                    session_id=self.session_id,
                )
            finally:
                await audio_queue.put(None)  # Sentinel

        # Launch LLM and TTS stages concurrently
        llm_task = asyncio.create_task(_llm_to_sentences())
        tts_task = asyncio.create_task(_tts_producer())

        try:
            # Yield audio chunks to the caller as they arrive
            while True:
                audio = await audio_queue.get()
                if audio is None:
                    break
                if self._cancelled:
                    break
                yield audio
        finally:
            # Ensure tasks are cleaned up
            if not llm_task.done():
                llm_task.cancel()
            if not tts_task.done():
                tts_task.cancel()

            # Await to suppress unhandled exceptions
            for task in (llm_task, tts_task):
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # Store assistant turn asynchronously
        response_text = " ".join(full_response_text)
        if response_text:
            asyncio.create_task(
                self._store_turn(
                    "assistant",
                    response_text,
                    detected_language,
                    metadata=self.metrics.summary(),
                )
            )

        logger.info(
            "pipeline_turn_complete",
            session_id=self.session_id,
            total_ms=round(self.metrics.total_ms, 1),
            ttfa_ms=round(self.metrics.time_to_first_audio_ms, 1),
            stages=self.metrics.summary().get("stages"),
        )

    async def _store_turn(
        self,
        role: str,
        content: str,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        """Store a conversation turn in the session manager (fire-and-forget)."""
        try:
            await session_client.add_turn(
                session_id=self.session_id,
                role=role,
                content=content,
                language=language,
                metadata=metadata,
            )
        except Exception as exc:
            logger.warning(
                "store_turn_failed",
                role=role,
                session_id=self.session_id,
                error=str(exc),
            )
