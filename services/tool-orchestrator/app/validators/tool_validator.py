"""Validation logic for tool requests."""

from __future__ import annotations

from shared.logging import get_logger

from app.models.requests import ToolRequest

logger = get_logger("tool_validator")

# Avoid circular import at module level; accept registry via constructor.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.tool_registry import ToolRegistry


class ToolValidator:
    """Validates tool requests before execution."""

    def __init__(self, registry: "ToolRegistry") -> None:
        self._registry = registry

    # ---------- Public validation entry point ----------

    def validate_request(self, request: ToolRequest) -> list[str]:
        """Validate a complete tool request.

        Returns a list of error messages. An empty list means the request
        is valid.
        """
        errors: list[str] = []
        errors.extend(self.validate_tool_name(request.tool_name))
        if not errors:
            errors.extend(self.validate_arguments(request.tool_name, request.arguments))
        errors.extend(self.validate_session_context(request.session_id))

        # Check patient_id requirement
        tool = self._registry.get_tool(request.tool_name)
        if tool and tool.requires_patient_id and not request.patient_id:
            errors.append(
                f"Tool '{request.tool_name}' requires a patient_id but none was provided."
            )

        if errors:
            logger.warning(
                "validation_failed",
                tool=request.tool_name,
                session_id=request.session_id,
                errors=errors,
            )

        return errors

    # ---------- Individual validators ----------

    def validate_tool_name(self, name: str) -> list[str]:
        """Check that the tool name is non-empty and registered.

        Args:
            name: Tool name to validate.

        Returns:
            List of error messages (empty if valid).
        """
        if not name or not name.strip():
            return ["Tool name must not be empty."]
        if not self._registry.has_tool(name):
            available = [t.name for t in self._registry.list_tools()]
            return [
                f"Unknown tool '{name}'. Available tools: {', '.join(available)}"
            ]
        return []

    def validate_arguments(self, tool_name: str, arguments: dict) -> list[str]:
        """Validate tool arguments against the registered parameter schema.

        Args:
            tool_name: Name of the tool.
            arguments: Arguments dict to validate.

        Returns:
            List of error messages (empty if valid).
        """
        return self._registry.validate_arguments(tool_name, arguments)

    @staticmethod
    def validate_session_context(session_id: str) -> list[str]:
        """Validate that a session_id is present.

        Args:
            session_id: Session identifier.

        Returns:
            List of error messages (empty if valid).
        """
        if not session_id or not session_id.strip():
            return ["session_id is required."]
        return []
