"""Structured logging configuration using structlog."""

import logging
import sys

import structlog


def setup_logging(service_name: str, log_level: str = "info") -> None:
    """Configure structured logging for a service.

    Args:
        service_name: Name of the service for log context.
        log_level: Logging level (debug, info, warning, error).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Set root logger level
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)

    # Bind service name to all log entries
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Optional logger name for context.

    Returns:
        Bound structured logger.
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger
