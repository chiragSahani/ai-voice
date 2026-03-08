"""Re-export TTS client from the unified gRPC clients module."""

from app.clients.grpc_clients import TTSClient

__all__ = ["TTSClient"]
