"""FastAPI route handlers for session management.

Each handler validates input, delegates to services, and returns
structured responses. Error handling is done via the middleware.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from shared.logging import get_logger

from app.models.requests import AddTurnRequest, CreateSessionRequest, UpdateSessionRequest
from app.models.responses import (
    ContextResponse,
    SessionListResponse,
    SessionResponse,
    TurnListResponse,
    TurnResponse,
)
from app.services import context_builder, session_service, turn_service
from app.validators.session_validator import (
    validate_create_session,
    validate_session_exists,
    validate_turn,
)

logger = get_logger("session_controller")

router = APIRouter(tags=["sessions"])


def _session_to_response(session) -> SessionResponse:
    """Convert a domain Session to a SessionResponse."""
    return SessionResponse(
        session_id=session.id,
        patient_id=session.patient_id,
        language=session.language,
        channel=session.channel,
        clinic_id=session.clinic_id,
        status=session.status.value if hasattr(session.status, "value") else session.status,
        turn_count=session.turn_count,
        metadata=session.metadata,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: Request, body: CreateSessionRequest) -> SessionResponse:
    """Create a new conversation session."""
    validate_create_session(body)

    redis = request.app.state.redis
    session = await session_service.create_session(
        redis=redis,
        patient_id=body.patient_id,
        language=body.language,
        channel=body.channel,
        clinic_id=body.clinic_id,
        metadata=body.metadata,
    )

    logger.info("session_created_via_api", session_id=session.id)
    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(request: Request, session_id: str) -> SessionResponse:
    """Get a session by ID."""
    redis = request.app.state.redis
    session = await session_service.get_session(redis, session_id)
    return _session_to_response(session)


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    request: Request, session_id: str, body: UpdateSessionRequest
) -> SessionResponse:
    """Update a session's mutable fields."""
    redis = request.app.state.redis
    await validate_session_exists(redis, session_id)

    session = await session_service.update_session(
        redis=redis,
        session_id=session_id,
        language=body.language,
        patient_context=body.patient_context,
        metadata=body.metadata,
    )

    return _session_to_response(session)


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
async def end_session(request: Request, session_id: str) -> SessionResponse:
    """End a session."""
    redis = request.app.state.redis
    session = await session_service.end_session(redis, session_id)
    return _session_to_response(session)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    clinic_id: str | None = Query(default=None, description="Filter by clinic ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
) -> SessionListResponse:
    """List sessions with optional filtering and pagination."""
    redis = request.app.state.redis
    sessions, total = await session_service.list_sessions(
        redis=redis,
        clinic_id=clinic_id,
        status=status,
        page=page,
        limit=limit,
    )

    return SessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("/sessions/{session_id}/turns", response_model=TurnResponse, status_code=201)
async def add_turn(
    request: Request, session_id: str, body: AddTurnRequest
) -> TurnResponse:
    """Add a conversation turn to a session."""
    redis = request.app.state.redis
    await validate_session_exists(redis, session_id)
    validate_turn(body)

    turn, index = await turn_service.add_turn(
        redis=redis,
        session_id=session_id,
        role=body.role,
        content=body.content,
        tool_calls=body.tool_calls,
        tool_results=body.tool_results,
        timestamp=body.timestamp,
    )

    return TurnResponse(
        index=index,
        role=turn.role.value if hasattr(turn.role, "value") else turn.role,
        content=turn.content,
        tool_calls=turn.tool_calls,
        tool_results=turn.tool_results,
        timestamp=turn.timestamp,
    )


@router.get("/sessions/{session_id}/turns", response_model=TurnListResponse)
async def get_turns(
    request: Request,
    session_id: str,
    limit: int = Query(default=0, ge=0, description="Max turns (0 = all)"),
    offset: int = Query(default=0, ge=0, description="Skip N turns"),
) -> TurnListResponse:
    """Get conversation turns for a session."""
    redis = request.app.state.redis
    await validate_session_exists(redis, session_id)

    turns, total = await turn_service.get_turns(
        redis=redis,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )

    turn_responses = [
        TurnResponse(
            index=offset + i,
            role=t.role.value if hasattr(t.role, "value") else t.role,
            content=t.content,
            tool_calls=t.tool_calls,
            tool_results=t.tool_results,
            timestamp=t.timestamp,
        )
        for i, t in enumerate(turns)
    ]

    return TurnListResponse(
        session_id=session_id,
        turns=turn_responses,
        total=total,
    )


@router.get("/sessions/{session_id}/context", response_model=ContextResponse)
async def get_context(request: Request, session_id: str) -> ContextResponse:
    """Build and return the LLM context for a session."""
    redis = request.app.state.redis
    await validate_session_exists(redis, session_id)

    ctx = await context_builder.build_context(redis, session_id)

    return ContextResponse(
        session_id=session_id,
        system_prompt=ctx.system_prompt,
        messages=ctx.messages,
        patient_context=ctx.patient_info,
        summary=ctx.summary,
        turn_count=ctx.turn_count,
        token_estimate=ctx.token_estimate,
    )


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
async def delete_session(request: Request, session_id: str) -> Response:
    """Delete a session and all associated data."""
    redis = request.app.state.redis
    await session_service.delete_session(redis, session_id)
    return Response(status_code=204)
