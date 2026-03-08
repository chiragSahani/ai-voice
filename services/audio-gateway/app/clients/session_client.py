"""HTTP client for the Session Manager service."""

from __future__ import annotations

import time
from typing import Any

import httpx

from shared.circuit_breaker import ServiceCircuitBreaker
from shared.logging import get_logger

from app.config import settings

logger = get_logger("session_client")


class SessionClient:
    """Async HTTP client for session CRUD operations against session-manager."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cb = ServiceCircuitBreaker(
            "session-manager",
            fail_max=settings.cb_fail_max,
            reset_timeout=settings.cb_reset_timeout,
        )

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.session_manager_url,
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"Content-Type": "application/json"},
        )
        logger.info("session_client_connected", url=settings.session_manager_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def create_session(
        self,
        patient_id: str | None = None,
        language: str = "en",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Create a new voice session.

        Args:
            patient_id: Optional patient identifier.
            language: Initial language.
            metadata: Additional session metadata.

        Returns:
            Session data dict with session_id, created_at, etc.
        """
        start = time.monotonic()
        payload = {
            "patient_id": patient_id,
            "language": language,
            "channel": "voice",
            "metadata": metadata or {},
        }

        try:
            resp = await self._client.post("/api/v1/sessions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "session_created",
                session_id=data.get("session_id"),
                latency_ms=round((time.monotonic() - start) * 1000, 1),
            )
            return data
        except httpx.HTTPError as exc:
            logger.error("session_create_failed", error=str(exc))
            raise

    async def get_session(self, session_id: str) -> dict | None:
        """Retrieve an existing session.

        Args:
            session_id: Session identifier.

        Returns:
            Session data dict or None if not found.
        """
        try:
            resp = await self._client.get(f"/api/v1/sessions/{session_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error("session_get_failed", session_id=session_id, error=str(exc))
            raise

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        language: str = "en",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Append a conversation turn to the session.

        Args:
            session_id: Session identifier.
            role: Turn role — "user" or "assistant".
            content: Text content.
            language: Language of this turn.
            metadata: Extra data (latency metrics, confidence, etc.).

        Returns:
            Updated session data.
        """
        payload = {
            "role": role,
            "content": content,
            "language": language,
            "timestamp_ms": int(time.time() * 1000),
            "metadata": metadata or {},
        }
        try:
            resp = await self._client.post(
                f"/api/v1/sessions/{session_id}/turns", json=payload
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error(
                "session_add_turn_failed",
                session_id=session_id,
                error=str(exc),
            )
            raise

    async def end_session(self, session_id: str) -> dict:
        """Mark a session as ended.

        Args:
            session_id: Session identifier.

        Returns:
            Final session data.
        """
        try:
            resp = await self._client.post(f"/api/v1/sessions/{session_id}/end")
            resp.raise_for_status()
            data = resp.json()
            logger.info("session_ended", session_id=session_id)
            return data
        except httpx.HTTPError as exc:
            logger.error("session_end_failed", session_id=session_id, error=str(exc))
            raise

    async def get_conversation_history(self, session_id: str) -> list[dict]:
        """Fetch conversation history for context.

        Args:
            session_id: Session identifier.

        Returns:
            List of turn dicts.
        """
        try:
            resp = await self._client.get(f"/api/v1/sessions/{session_id}/turns")
            resp.raise_for_status()
            return resp.json().get("turns", [])
        except httpx.HTTPError as exc:
            logger.error(
                "session_history_failed",
                session_id=session_id,
                error=str(exc),
            )
            return []

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False


session_client = SessionClient()
