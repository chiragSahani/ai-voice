"""gRPC client stubs for downstream services.

The STT service is primarily a server, but may need to notify
downstream services (e.g., session-manager) of transcription events.
"""

from typing import Optional

import grpc

from shared.grpc_utils import create_grpc_channel
from shared.logging import get_logger

logger = get_logger("grpc_clients")


class SessionManagerClient:
    """Client for the session-manager service to publish transcription events."""

    def __init__(self, target: str = "session-manager:6380") -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None

    async def connect(self) -> None:
        """Establish the gRPC channel."""
        self._channel = create_grpc_channel(self._target)
        logger.info("session_manager_client_connected", target=self._target)

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            logger.info("session_manager_client_closed")

    async def notify_transcription(
        self,
        session_id: str,
        text: str,
        language: str,
        is_final: bool,
    ) -> None:
        """Notify session manager of a transcription event.

        This is a fire-and-forget notification; failures are logged
        but do not affect the STT pipeline.
        """
        if self._channel is None:
            logger.debug("session_manager_not_connected_skipping_notification")
            return

        try:
            # Notification would go here via the session manager's gRPC API.
            # Currently the session manager uses Redis Streams, so this client
            # is reserved for future direct gRPC communication.
            logger.debug(
                "transcription_notification_sent",
                session_id=session_id,
                is_final=is_final,
            )
        except Exception as exc:
            logger.warning(
                "transcription_notification_failed",
                session_id=session_id,
                error=str(exc),
            )
