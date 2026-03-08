"""Handler for the book_appointment tool."""

from __future__ import annotations

from shared.logging import get_logger

from app.clients.http_client import AppointmentSchedulerClient
from app.models.domain import ToolExecutionContext

logger = get_logger("handler.book_appointment")


async def handle_book_appointment(
    context: ToolExecutionContext,
    client: AppointmentSchedulerClient,
    *,
    patient_id: str,
    slot_id: str,
    appointment_type: str = "consultation",
    reason: str = "",
) -> dict:
    """Book an appointment for a patient.

    Args:
        context: Execution context with session/correlation IDs.
        client: Appointment scheduler HTTP client.
        patient_id: The patient's identifier.
        slot_id: The slot identifier to book.
        appointment_type: Type of appointment (consultation, follow-up, etc.).
        reason: Reason for the appointment.

    Returns:
        Dict with appointment confirmation details.
    """
    logger.info(
        "book_appointment",
        session_id=context.session_id,
        correlation_id=context.correlation_id,
        patient_id=patient_id,
        slot_id=slot_id,
        appointment_type=appointment_type,
    )

    result = await client.book_appointment(
        patient_id=patient_id,
        slot_id=slot_id,
        appointment_type=appointment_type,
        reason=reason,
    )

    appointment = result.get("appointment", result.get("data", result))
    return {
        "appointment": appointment,
        "status": "booked",
        "message": "Appointment booked successfully.",
    }
