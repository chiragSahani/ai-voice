"""Re-export LLM client from the unified gRPC clients module."""

from app.clients.grpc_clients import LLMClient

__all__ = ["LLMClient"]
