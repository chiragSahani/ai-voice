"""gRPC service registration for the LLM Agent."""

import grpc

from shared.logging import get_logger

from app.controllers.agent_controller import LLMAgentServicer

logger = get_logger("routes")


def register_grpc_services(
    server: grpc.aio.Server,
    servicer: LLMAgentServicer,
) -> None:
    """Register the LLMAgent gRPC servicer on the server.

    Args:
        server: gRPC async server instance.
        servicer: LLMAgentServicer instance.
    """
    from generated import llm_agent_pb2_grpc

    llm_agent_pb2_grpc.add_LLMAgentServicer_to_server(servicer, server)

    logger.info("grpc_services_registered", service="LLMAgent")
