"""Handler for the lookup_patient tool."""

from __future__ import annotations

from shared.logging import get_logger

from app.clients.http_client import PatientMemoryClient
from app.models.domain import ToolExecutionContext

logger = get_logger("handler.lookup_patient")


async def handle_lookup_patient(
    context: ToolExecutionContext,
    client: PatientMemoryClient,
    *,
    phone: str = "",
    name: str = "",
    mrn: str = "",
) -> dict:
    """Look up a patient by phone number, name, or MRN.

    Args:
        context: Execution context with session/correlation IDs.
        client: Patient memory HTTP client.
        phone: Patient phone number.
        name: Patient name (partial match).
        mrn: Medical Record Number.

    Returns:
        Dict with patient information.
    """
    logger.info(
        "lookup_patient",
        session_id=context.session_id,
        correlation_id=context.correlation_id,
        has_phone=bool(phone),
        has_name=bool(name),
        has_mrn=bool(mrn),
    )

    result = await client.lookup_patient(
        phone=phone,
        name=name,
        mrn=mrn,
    )

    patients = result.get("patients", result.get("data", []))
    return {
        "patients": patients,
        "count": len(patients) if isinstance(patients, list) else 0,
        "message": (
            f"Found {len(patients)} matching patient(s)."
            if isinstance(patients, list) and patients
            else "No matching patients found."
        ),
    }
