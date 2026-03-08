"""WebSocket connection lifecycle manager.

Tracks active connections, enforces max-connection limits,
and provides broadcast capabilities for admin notifications.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket

from shared.logging import get_logger
from shared.metrics import create_request_metrics

from app.config import settings
from app.models.domain import ConnectionState
from app.models.responses import WSResponse

logger = get_logger("connection_manager")

# Prometheus metrics
_metrics = create_request_metrics("audio_gateway")


class ConnectionManager:
    """Thread-safe manager for active WebSocket connections."""

    def __init__(self, max_connections: int = 200) -> None:
        self._connections: dict[str, tuple[WebSocket, ConnectionState]] = {}
        self._lock = asyncio.Lock()
        self._max_connections = max_connections

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def add_connection(
        self,
        websocket: WebSocket,
        session_id: str,
        patient_id: str | None = None,
        language: str = "en",
    ) -> ConnectionState:
        """Register a new WebSocket connection.

        Args:
            websocket: The accepted WebSocket.
            session_id: Session identifier.
            patient_id: Optional patient identifier.
            language: Initial language.

        Returns:
            ConnectionState for this connection.

        Raises:
            RuntimeError: If max connections exceeded.
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                raise RuntimeError(
                    f"Max connections ({self._max_connections}) exceeded"
                )

            # If session already has a connection, close the old one
            if session_id in self._connections:
                old_ws, old_state = self._connections[session_id]
                logger.warning(
                    "replacing_existing_connection",
                    session_id=session_id,
                    old_connected_at=old_state.connected_at,
                )
                try:
                    await old_ws.close(code=1000, reason="Replaced by new connection")
                except Exception:
                    pass

            state = ConnectionState(
                session_id=session_id,
                patient_id=patient_id,
                language=language,
            )
            self._connections[session_id] = (websocket, state)

        _metrics["active_connections"].set(len(self._connections))
        logger.info(
            "connection_added",
            session_id=session_id,
            active_connections=len(self._connections),
        )
        return state

    async def remove_connection(self, session_id: str) -> ConnectionState | None:
        """Remove and return the connection state for a session.

        Args:
            session_id: Session identifier.

        Returns:
            The removed ConnectionState, or None if not found.
        """
        async with self._lock:
            entry = self._connections.pop(session_id, None)

        if entry:
            _, state = entry
            _metrics["active_connections"].set(len(self._connections))
            duration = time.time() - state.connected_at
            logger.info(
                "connection_removed",
                session_id=session_id,
                duration_s=round(duration, 1),
                turns=state.turn_count,
                active_connections=len(self._connections),
            )
            return state
        return None

    def get_connection(self, session_id: str) -> tuple[WebSocket, ConnectionState] | None:
        """Look up an active connection by session ID.

        Args:
            session_id: Session identifier.

        Returns:
            Tuple of (WebSocket, ConnectionState) or None.
        """
        return self._connections.get(session_id)

    def get_state(self, session_id: str) -> ConnectionState | None:
        """Get just the connection state (no WebSocket ref)."""
        entry = self._connections.get(session_id)
        return entry[1] if entry else None

    async def broadcast(self, message: WSResponse) -> int:
        """Send a message to all connected clients.

        Args:
            message: WSResponse to broadcast.

        Returns:
            Number of clients successfully reached.
        """
        data = message.to_json_bytes()
        sent = 0
        failed_sessions: list[str] = []

        for session_id, (ws, _) in list(self._connections.items()):
            try:
                await ws.send_bytes(data)
                sent += 1
            except Exception:
                failed_sessions.append(session_id)

        # Clean up dead connections
        for sid in failed_sessions:
            await self.remove_connection(sid)

        if failed_sessions:
            logger.warning(
                "broadcast_failures",
                failed=len(failed_sessions),
                sent=sent,
            )
        return sent

    async def send_to(self, session_id: str, message: WSResponse) -> bool:
        """Send a message to a specific session.

        Args:
            session_id: Target session.
            message: WSResponse to send.

        Returns:
            True if sent successfully.
        """
        entry = self._connections.get(session_id)
        if not entry:
            return False
        ws, _ = entry
        try:
            await ws.send_text(message.model_dump_json())
            return True
        except Exception as exc:
            logger.warning("send_failed", session_id=session_id, error=str(exc))
            return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active sessions (for admin/metrics endpoints)."""
        result = []
        for session_id, (_, state) in self._connections.items():
            result.append({
                "session_id": session_id,
                "patient_id": state.patient_id,
                "language": state.language,
                "connected_at": state.connected_at,
                "turn_count": state.turn_count,
                "is_processing": state.is_processing,
            })
        return result


# Module-level singleton
connection_manager = ConnectionManager(max_connections=settings.ws_max_connections)
