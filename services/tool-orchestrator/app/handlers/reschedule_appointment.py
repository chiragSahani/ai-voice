"""Handler for the reschedule_appointment tool."""

from __future__ import annotations

from shared.logging import get_logger

from app.clients.http_client import AppointmentSchedulerClient
from app.models.domain import ToolExecutionContext

logger = get_logger("handler.reschedule_appointment")


async def handle_reschedule_appointment(
    context: ToolExecutionContext,
    client: AppointmentSchedulerClient,
    *,
    appointment_id: str,
    new_slot_id: str,
) -> dict:
    """Reschedule an appointment to a different slot.

    Args:
        context: Execution context with session/correlation IDs.
        client: Appointment scheduler HTTP client.
        appointment_id: The appointment to reschedule.
        new_slot_id: The new slot identifier.

    Returns:
        Dict with rescheduled appointment details.
    """
    logger.info(
        "reschedule_appointment",
        session_id=context.session_id,
        correlation_id=context.correlation_id,
        appointment_id=appointment_id,
        new_slot_id=new_slot_id,
    )

    result = await client.reschedule_appointment(
        appointment_id=appointment_id,
        new_slot_id=new_slot_id,
    )

    appointment = result.get("appointment", result.get("data", result))
    return {
        "appointment": appointment,
        "status": "rescheduled",
        "message": "Appointment rescheduled successfully.",
    }
