"""API v1 route registration with /api/v1 prefix."""

from fastapi import APIRouter

from app.controllers.session_controller import router as session_router

api_v1_router = APIRouter(prefix="/api/v1")

# Include session routes
api_v1_router.include_router(session_router)
