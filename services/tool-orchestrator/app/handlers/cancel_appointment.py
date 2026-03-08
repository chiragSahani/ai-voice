"""Handler for the cancel_appointment tool."""

from __future__ import annotations

from shared.logging import get_logger

from app.clients.http_client import AppointmentSchedulerClient
from app.models.domain import ToolExecutionContext

logger = get_logger("handler.cancel_appointment")


async def handle_cancel_appointment(
    context: ToolExecutionContext,
    client: AppointmentSchedulerClient,
    *,
    appointment_id: str,
    reason: str = "",
) -> dict:
    """Cancel an existing appointment.

    Args:
        context: Execution context with session/correlation IDs.
        client: Appointment scheduler HTTP client.
        appointment_id: The appointment to cancel.
        reason: Cancellation reason.

    Returns:
        Dict with cancellation confirmation.
    """
    logger.info(
        "cancel_appointment",
        session_id=context.session_id,
        correlation_id=context.correlation_id,
        appointment_id=appointment_id,
    )

    result = await client.cancel_appointment(
        appointment_id=appointment_id,
        reason=reason,
    )

    return {
        "appointment_id": appointment_id,
        "status": "cancelled",
        "message": result.get("message", "Appointment cancelled successfully."),
    }
