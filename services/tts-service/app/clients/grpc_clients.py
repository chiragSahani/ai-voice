"""Outbound gRPC client stubs for TTS service.

The TTS service is primarily a server, but may need to call other
services (e.g., session-manager for session validation). This module
provides lazy-initialized gRPC client channels.
"""

import grpc

from app.config import TTSConfig
from shared.grpc_utils import create_grpc_channel
from shared.logging import get_logger

logger = get_logger("grpc_clients")

_channels: dict[str, grpc.aio.Channel] = {}


async def get_session_channel(config: TTSConfig) -> grpc.aio.Channel:
    """Get or create a gRPC channel to the session manager.

    Args:
        config: TTS configuration with service addresses.

    Returns:
        gRPC async channel to session-manager.
    """
    key = "session_manager"
    if key not in _channels:
        target = f"session-manager:{config.redis_url.split(':')[-1] if ':' in config.redis_url else '6380'}"
        _channels[key] = create_grpc_channel(target)
        logger.info("session_channel_created", target=target)
    return _channels[key]


async def close_all_channels() -> None:
    """Close all open gRPC client channels."""
    for name, channel in _channels.items():
        await channel.close()
        logger.info("grpc_channel_closed", channel=name)
    _channels.clear()
