"""Tool registry - registers all available tools and validates arguments."""

from __future__ import annotations

from shared.logging import get_logger

from app.handlers import (
    handle_book_appointment,
    handle_cancel_appointment,
    handle_check_availability,
    handle_lookup_patient,
    handle_reschedule_appointment,
)
from app.models.domain import ToolDefinition
from app.models.responses import ToolInfo

logger = get_logger("tool_registry")


# ---------- JSON Schemas for tool parameters ----------

CHECK_AVAILABILITY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "doctor_id": {
            "type": "string",
            "description": "Doctor's unique identifier.",
        },
        "specialization": {
            "type": "string",
            "description": "Medical specialization (e.g. cardiology, dermatology).",
        },
        "date": {
            "type": "string",
            "format": "date",
            "description": "Date to check in YYYY-MM-DD format.",
        },
        "time_range": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "Start time HH:MM."},
                "to": {"type": "string", "description": "End time HH:MM."},
            },
            "description": "Optional time window filter.",
        },
    },
    "required": [],
}

BOOK_APPOINTMENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "patient_id": {
            "type": "string",
            "description": "Patient's unique identifier.",
        },
        "slot_id": {
            "type": "string",
            "description": "Available slot identifier to book.",
        },
        "appointment_type": {
            "type": "string",
            "enum": ["consultation", "follow-up", "emergency", "routine"],
            "description": "Type of appointment.",
            "default": "consultation",
        },
        "reason": {
            "type": "string",
            "description": "Reason for the visit.",
        },
    },
    "required": ["patient_id", "slot_id"],
}

CANCEL_APPOINTMENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "appointment_id": {
            "type": "string",
            "description": "Appointment identifier to cancel.",
        },
        "reason": {
            "type": "string",
            "description": "Cancellation reason.",
        },
    },
    "required": ["appointment_id"],
}

RESCHEDULE_APPOINTMENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "appointment_id": {
            "type": "string",
            "description": "Appointment identifier to reschedule.",
        },
        "new_slot_id": {
            "type": "string",
            "description": "New slot identifier.",
        },
    },
    "required": ["appointment_id", "new_slot_id"],
}

LOOKUP_PATIENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "phone": {
            "type": "string",
            "description": "Patient's phone number.",
        },
        "name": {
            "type": "string",
            "description": "Patient's name (partial match supported).",
        },
        "mrn": {
            "type": "string",
            "description": "Medical Record Number.",
        },
    },
    "required": [],
    "minProperties": 1,
}


class ToolRegistry:
    """Central registry for all available tools.

    Provides tool lookup, listing, and argument validation.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_all()

    def _register_all(self) -> None:
        """Register every tool the orchestrator supports."""
        self._register(
            ToolDefinition(
                name="check_availability",
                description=(
                    "Check available appointment slots for a doctor or specialization "
                    "on a given date. Returns a list of bookable time slots."
                ),
                handler=handle_check_availability,
                parameter_schema=CHECK_AVAILABILITY_SCHEMA,
                requires_patient_id=False,
            )
        )
        self._register(
            ToolDefinition(
                name="book_appointment",
                description=(
                    "Book an appointment for a patient in an available slot. "
                    "Requires patient_id and slot_id."
                ),
                handler=handle_book_appointment,
                parameter_schema=BOOK_APPOINTMENT_SCHEMA,
                requires_patient_id=True,
            )
        )
        self._register(
            ToolDefinition(
                name="cancel_appointment",
                description=(
                    "Cancel an existing appointment. Requires the appointment_id."
                ),
                handler=handle_cancel_appointment,
                parameter_schema=CANCEL_APPOINTMENT_SCHEMA,
                requires_patient_id=True,
            )
        )
        self._register(
            ToolDefinition(
                name="reschedule_appointment",
                description=(
                    "Reschedule an existing appointment to a new time slot. "
                    "Requires appointment_id and new_slot_id."
                ),
                handler=handle_reschedule_appointment,
                parameter_schema=RESCHEDULE_APPOINTMENT_SCHEMA,
                requires_patient_id=True,
            )
        )
        self._register(
            ToolDefinition(
                name="lookup_patient",
                description=(
                    "Look up patient information by phone number, name, or "
                    "Medical Record Number. At least one search criterion is required."
                ),
                handler=handle_lookup_patient,
                parameter_schema=LOOKUP_PATIENT_SCHEMA,
                requires_patient_id=False,
            )
        )
        logger.info("tools_registered", count=len(self._tools))

    def _register(self, tool: ToolDefinition) -> None:
        """Register a single tool definition."""
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name.

        Args:
            name: The tool name.

        Returns:
            ToolDefinition if found, None otherwise.
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check whether a tool with the given name is registered."""
        return name in self._tools

    def list_tools(self) -> list[ToolInfo]:
        """Return metadata for all registered tools.

        Returns:
            List of ToolInfo objects suitable for LLM function spec generation.
        """
        return [
            ToolInfo(
                name=t.name,
                description=t.description,
                parameters_schema=t.parameter_schema,
                requires_patient_id=t.requires_patient_id,
                required_permissions=t.required_permissions,
            )
            for t in self._tools.values()
        ]

    def validate_arguments(self, tool_name: str, arguments: dict) -> list[str]:
        """Validate arguments against the tool's parameter schema.

        Checks required parameters and basic type constraints. Returns a list
        of validation error strings (empty if valid).

        Args:
            tool_name: Name of the tool.
            arguments: Provided arguments dict.

        Returns:
            List of human-readable error messages.
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            return [f"Unknown tool: {tool_name}"]

        schema = tool.parameter_schema
        errors: list[str] = []

        # Check required parameters
        for param in schema.get("required", []):
            if param not in arguments or arguments[param] in (None, ""):
                errors.append(f"Missing required parameter: {param}")

        # Check minProperties (e.g. lookup_patient needs at least one field)
        min_props = schema.get("minProperties", 0)
        if min_props > 0:
            non_empty = sum(
                1 for v in arguments.values() if v not in (None, "", {})
            )
            if non_empty < min_props:
                errors.append(
                    f"At least {min_props} parameter(s) must be provided."
                )

        # Check parameter names are valid
        known_params = set(schema.get("properties", {}).keys())
        if known_params:
            for key in arguments:
                if key not in known_params:
                    errors.append(f"Unknown parameter: {key}")

        # Basic type checking
        properties = schema.get("properties", {})
        for key, value in arguments.items():
            if key in properties and value is not None:
                expected_type = properties[key].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(
                        f"Parameter '{key}' must be a string, got {type(value).__name__}."
                    )
                elif expected_type == "object" and not isinstance(value, dict):
                    errors.append(
                        f"Parameter '{key}' must be an object, got {type(value).__name__}."
                    )

                # Enum validation
                allowed = properties[key].get("enum")
                if allowed and value not in allowed:
                    errors.append(
                        f"Parameter '{key}' must be one of {allowed}, got '{value}'."
                    )

        return errors
