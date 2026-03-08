"""REST API v1 routes for the Tool Orchestrator.

These HTTP endpoints complement the primary gRPC interface and are useful
for debugging, health checks, and lightweight integrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from app.models.requests import BatchToolRequest, ToolRequest
from app.models.responses import BatchToolResponse, ToolInfo, ToolResponse

if TYPE_CHECKING:
    from app.services.orchestrator_service import ExecutionService
    from app.services.tool_registry import ToolRegistry

router = APIRouter(prefix="/api/v1", tags=["tools"])

# These will be set during application startup via `configure_routes`.
_execution_service: "ExecutionService | None" = None
_registry: "ToolRegistry | None" = None


def configure_routes(
    execution_service: "ExecutionService",
    registry: "ToolRegistry",
) -> None:
    """Inject runtime dependencies into the route module.

    Called once from ``main.py`` during application startup.
    """
    global _execution_service, _registry  # noqa: PLW0603
    _execution_service = execution_service
    _registry = registry


def _get_execution_service() -> "ExecutionService":
    if _execution_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _execution_service


def _get_registry() -> "ToolRegistry":
    if _registry is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _registry


# ---------- Endpoints ----------


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools() -> list[ToolInfo]:
    """List all available tools and their parameter schemas."""
    registry = _get_registry()
    return registry.list_tools()


@router.post("/tools/execute", response_model=ToolResponse)
async def execute_tool(request: ToolRequest) -> ToolResponse:
    """Execute a single tool."""
    service = _get_execution_service()
    return await service.execute_tool(request)


@router.post("/tools/execute-batch", response_model=BatchToolResponse)
async def execute_tool_batch(request: BatchToolRequest) -> BatchToolResponse:
    """Execute multiple tools in parallel."""
    service = _get_execution_service()
    return await service.execute_batch(request)


@router.get("/tools/metrics")
async def tool_metrics() -> dict:
    """Return per-tool execution metrics."""
    from app.services.orchestrator_service import ExecutionService

    return ExecutionService.get_metrics()
