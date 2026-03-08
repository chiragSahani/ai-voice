"""WebSocket controller — handles the full lifecycle of a voice session.

Flow:
    1. Client connects to /ws/audio?token=...&language=en&session_id=...
    2. Server authenticates, creates/resumes session via session-manager.
    3. Client sends binary audio frames; server streams them through the
       voice pipeline (STT -> LLM -> TTS).
    4. Server sends back JSON transcript events and binary audio responses.
    5. Client can send JSON control messages (end_session, change_language,
       interrupt, ping).
    6. On disconnect, cleanup and end session.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from shared.logging import get_logger

from app.clients.session_client import session_client
from app.config import settings
from app.models.domain import ConnectionState
from app.models.requests import ControlMessage
from app.models.responses import (
    AudioResponseMessage,
    ErrorMessage,
    StatusMessage,
    TranscriptMessage,
    WSResponse,
)
from app.services.audio_processor import compute_audio_duration_ms
from app.services.connection_manager import connection_manager
from app.services.pipeline_service import VoicePipeline
from app.validators.audio_validator import (
    validate_audio_chunk,
    validate_auth_token,
    validate_session_params,
)

logger = get_logger("ws_controller")


async def handle_connection(websocket: WebSocket) -> None:
    """Main WebSocket lifecycle handler.

    Args:
        websocket: The incoming WebSocket connection.
    """
    session_id: str | None = None
    conn_state: ConnectionState | None = None
    current_pipeline: VoicePipeline | None = None

    try:
        # ---- 1. Extract query parameters ----
        token = websocket.query_params.get("token", "")
        language = websocket.query_params.get("language", "en")
        requested_session_id = websocket.query_params.get("session_id")
        patient_id = websocket.query_params.get("patient_id")

        # ---- 2. Authenticate ----
        try:
            user_info = validate_auth_token(token)
            if patient_id is None:
                patient_id = user_info.get("patient_id")
        except Exception as auth_exc:
            await websocket.accept()
            await _send_error(websocket, "AUTH_FAILED", str(auth_exc))
            await websocket.close(code=4001, reason="Authentication failed")
            return

        # ---- 3. Validate parameters ----
        try:
            validate_session_params(requested_session_id, language)
        except Exception as val_exc:
            await websocket.accept()
            await _send_error(websocket, "INVALID_PARAMS", str(val_exc))
            await websocket.close(code=4002, reason="Invalid parameters")
            return

        # ---- 4. Accept the WebSocket ----
        await websocket.accept()

        # ---- 5. Create or resume session ----
        try:
            if requested_session_id:
                session_data = await session_client.get_session(requested_session_id)
                if session_data:
                    session_id = requested_session_id
                    logger.info("session_resumed", session_id=session_id)
                else:
                    session_data = await session_client.create_session(
                        patient_id=patient_id,
                        language=language,
                    )
                    session_id = session_data.get("session_id", str(uuid.uuid4()))
            else:
                session_data = await session_client.create_session(
                    patient_id=patient_id,
                    language=language,
                )
                session_id = session_data.get("session_id", str(uuid.uuid4()))
        except Exception as sess_exc:
            # Session manager unavailable — generate a local session ID
            # and proceed (graceful degradation).
            logger.warning(
                "session_manager_unavailable",
                error=str(sess_exc),
            )
            session_id = requested_session_id or str(uuid.uuid4())

        # ---- 6. Register connection ----
        conn_state = await connection_manager.add_connection(
            websocket=websocket,
            session_id=session_id,
            patient_id=patient_id,
            language=language,
        )

        # Send connected status to client
        await _send_status(
            websocket,
            "connected",
            f"Session {session_id} ready",
        )

        logger.info(
            "ws_connected",
            session_id=session_id,
            patient_id=patient_id,
            language=language,
        )

        # ---- 7. Message loop ----
        # Audio chunks accumulate in a queue; when the client stops sending
        # (VAD endpoint detected on client side, or silence timeout),
        # we process a turn.
        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=500)
        turn_active = False

        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            msg_type = message.get("type")

            if msg_type == "websocket.disconnect":
                break

            # -- Binary frame: audio data --
            if msg_type == "websocket.receive" and "bytes" in message:
                raw_bytes = message["bytes"]
                if not raw_bytes:
                    continue

                try:
                    validate_audio_chunk(raw_bytes)
                except Exception:
                    continue  # Drop invalid chunks silently for performance

                # If no turn is active, start one
                if not turn_active:
                    turn_active = True
                    conn_state.is_processing = True
                    conn_state.increment_turn()

                    # Launch pipeline consumer in background
                    current_pipeline = VoicePipeline(
                        session_id=session_id,
                        language=conn_state.language,
                    )

                    asyncio.create_task(
                        _run_turn(
                            websocket=websocket,
                            pipeline=current_pipeline,
                            audio_queue=audio_queue,
                            conn_state=conn_state,
                            session_id=session_id,
                        )
                    )

                await audio_queue.put(raw_bytes)

            # -- Text frame: control message --
            elif msg_type == "websocket.receive" and "text" in message:
                try:
                    data = json.loads(message["text"])
                    control = ControlMessage(**data)
                except (json.JSONDecodeError, Exception):
                    await _send_error(websocket, "INVALID_MESSAGE", "Malformed JSON")
                    continue

                if control.type == "end_turn":
                    # Signal end of audio for this turn
                    await audio_queue.put(None)
                    turn_active = False

                elif control.type == "end_session":
                    await audio_queue.put(None)
                    break

                elif control.type == "change_language":
                    new_lang = control.data.get("language", "en")
                    conn_state.language = new_lang
                    await _send_status(
                        websocket, "language_changed", f"Language set to {new_lang}"
                    )

                elif control.type == "interrupt":
                    if current_pipeline:
                        current_pipeline.cancel()
                    await audio_queue.put(None)
                    turn_active = False
                    await _send_status(websocket, "interrupted", "Playback stopped")

                elif control.type == "ping":
                    await _send_json(websocket, WSResponse(type="pong", data={}))

                else:
                    logger.debug(
                        "unknown_control_message",
                        type=control.type,
                        session_id=session_id,
                    )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(
            "ws_unhandled_error",
            error=str(exc),
            error_type=type(exc).__name__,
            session_id=session_id,
        )
    finally:
        # ---- Cleanup ----
        if current_pipeline:
            current_pipeline.cancel()

        if session_id:
            await connection_manager.remove_connection(session_id)

            # End session in session-manager (fire-and-forget)
            try:
                await session_client.end_session(session_id)
            except Exception:
                pass

        logger.info("ws_disconnected", session_id=session_id)


async def _run_turn(
    websocket: WebSocket,
    pipeline: VoicePipeline,
    audio_queue: asyncio.Queue[bytes | None],
    conn_state: ConnectionState,
    session_id: str,
) -> None:
    """Execute a single voice turn — reads from audio_queue, runs pipeline,
    sends responses back over the WebSocket.
    """
    try:
        # Fetch conversation history for LLM context
        try:
            history = await session_client.get_conversation_history(session_id)
        except Exception:
            history = []

        async def _audio_from_queue() -> asyncio.AsyncIterator[bytes]:
            """Yield audio chunks from the queue until sentinel."""
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    return
                yield chunk

        # Callback for sending transcript events to client
        async def _on_transcript(msg: TranscriptMessage) -> None:
            if websocket.client_state == WebSocketState.CONNECTED:
                await _send_json(websocket, msg.to_ws_response())

        # Run the pipeline and stream audio back
        seq = 0
        async for audio_bytes in pipeline.process_turn(
            audio_chunks=_audio_from_queue(),
            conversation_history=history,
            on_transcript=_on_transcript,
        ):
            if websocket.client_state != WebSocketState.CONNECTED:
                break

            # Send binary audio frame
            await websocket.send_bytes(audio_bytes)

            # Send accompanying metadata as JSON
            duration = compute_audio_duration_ms(audio_bytes, settings.audio_sample_rate)
            meta = AudioResponseMessage(
                sequence=seq,
                is_final=False,
                duration_ms=duration,
            )
            await _send_json(websocket, meta.to_ws_response())
            seq += 1

        # Signal end of audio
        if websocket.client_state == WebSocketState.CONNECTED:
            final_meta = AudioResponseMessage(sequence=seq, is_final=True, duration_ms=0)
            await _send_json(websocket, final_meta.to_ws_response())

            # Send pipeline metrics
            await _send_json(
                websocket,
                WSResponse(type="metrics", data=pipeline.metrics.summary()),
            )

    except Exception as exc:
        logger.error(
            "turn_error",
            error=str(exc),
            session_id=session_id,
        )
        if websocket.client_state == WebSocketState.CONNECTED:
            await _send_error(websocket, "PIPELINE_ERROR", str(exc))
    finally:
        conn_state.is_processing = False


async def _send_json(websocket: WebSocket, response: WSResponse) -> None:
    """Send a JSON response over the WebSocket."""
    try:
        await websocket.send_text(response.model_dump_json())
    except Exception:
        pass


async def _send_status(websocket: WebSocket, status: str, message: str) -> None:
    """Send a status message."""
    msg = StatusMessage(status=status, message=message)
    await _send_json(websocket, msg.to_ws_response())


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    """Send an error message."""
    msg = ErrorMessage(code=code, message=message)
    await _send_json(websocket, msg.to_ws_response())
