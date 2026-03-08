"""STT service route registration."""

from app.routes.v1 import register_grpc_services

__all__ = ["register_grpc_services"]
