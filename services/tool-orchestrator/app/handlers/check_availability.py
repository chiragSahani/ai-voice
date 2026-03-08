"""Handler for the check_availability tool."""

from __future__ import annotations

from shared.logging import get_logger

from app.clients.http_client import AppointmentSchedulerClient
from app.models.domain import ToolExecutionContext

logger = get_logger("handler.check_availability")


async def handle_check_availability(
    context: ToolExecutionContext,
    client: AppointmentSchedulerClient,
    *,
    doctor_id: str = "",
    specialization: str = "",
    date: str = "",
    time_range: dict | None = None,
) -> dict:
    """Check available appointment slots.

    Args:
        context: Execution context with session/correlation IDs.
        client: Appointment scheduler HTTP client.
        doctor_id: Optional doctor identifier.
        specialization: Optional specialization filter (e.g. 'cardiology').
        date: Date in YYYY-MM-DD format.
        time_range: Optional dict with 'from' and 'to' time strings (HH:MM).

    Returns:
        Dict with available slots.
    """
    logger.info(
        "check_availability",
        session_id=context.session_id,
        correlation_id=context.correlation_id,
        doctor_id=doctor_id,
        specialization=specialization,
        date=date,
    )

    result = await client.check_availability(
        doctor_id=doctor_id,
        specialization=specialization,
        date=date,
        time_range=time_range,
    )

    slots = result.get("slots", result.get("data", []))
    return {
        "available_slots": slots,
        "count": len(slots) if isinstance(slots, list) else 0,
        "date": date,
        "doctor_id": doctor_id,
        "specialization": specialization,
    }
