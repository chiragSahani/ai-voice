"""Re-export STT client from the unified gRPC clients module."""

from app.clients.grpc_clients import STTClient

__all__ = ["STTClient"]
