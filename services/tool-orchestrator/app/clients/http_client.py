"""Async HTTP client for downstream services with circuit breaker and retry."""

from __future__ import annotations

import time
from typing import Any

import httpx

from shared.circuit_breaker import ServiceCircuitBreaker
from shared.exceptions import ServiceUnavailableError
from shared.logging import get_logger

from app.config import get_config

logger = get_logger("http_client")


class DownstreamClient:
    """Base async HTTP client with circuit breaker, timeout, and retry."""

    def __init__(
        self,
        base_url: str,
        service_name: str,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        config = get_config()
        self._base_url = base_url.rstrip("/")
        self._service_name = service_name
        self._timeout = timeout or config.request_timeout
        self._max_retries = max_retries if max_retries is not None else config.request_max_retries
        self._retry_backoff = config.request_retry_backoff

        self._circuit_breaker = ServiceCircuitBreaker(
            service_name=service_name,
            fail_max=config.circuit_breaker_fail_max,
            reset_timeout=config.circuit_breaker_reset_timeout,
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                headers={"Content-Type": "application/json"},
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Execute an HTTP request through the circuit breaker.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: URL path relative to the base URL.
            data: JSON body payload.
            params: Query parameters.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            ServiceUnavailableError: If the downstream service is unreachable.
        """

        async def _do_request() -> dict:
            client = await self._get_client()
            last_exc: Exception | None = None
            for attempt in range(1 + self._max_retries):
                try:
                    start = time.monotonic()
                    response = await client.request(
                        method=method.upper(),
                        url=path,
                        json=data,
                        params=params,
                    )
                    duration_ms = round((time.monotonic() - start) * 1000, 2)
                    logger.debug(
                        "downstream_request",
                        service=self._service_name,
                        method=method.upper(),
                        path=path,
                        status=response.status_code,
                        duration_ms=duration_ms,
                        attempt=attempt + 1,
                    )
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    # Do not retry 4xx client errors
                    if 400 <= exc.response.status_code < 500:
                        raise
                    last_exc = exc
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_exc = exc

                if attempt < self._max_retries:
                    import asyncio

                    wait = self._retry_backoff * (2 ** attempt)
                    logger.warning(
                        "downstream_retry",
                        service=self._service_name,
                        path=path,
                        attempt=attempt + 1,
                        wait_s=wait,
                    )
                    await asyncio.sleep(wait)

            logger.error(
                "downstream_request_failed",
                service=self._service_name,
                path=path,
                error=str(last_exc),
            )
            raise ServiceUnavailableError(self._service_name)

        return await self._circuit_breaker.call_async(_do_request)


class AppointmentSchedulerClient(DownstreamClient):
    """HTTP client for the Appointment Scheduler service."""

    def __init__(self) -> None:
        config = get_config()
        super().__init__(
            base_url=config.appointment_scheduler_url,
            service_name="appointment-scheduler",
        )

    async def check_availability(
        self,
        doctor_id: str = "",
        specialization: str = "",
        date: str = "",
        time_range: dict[str, str] | None = None,
    ) -> dict:
        """Check available appointment slots."""
        params: dict[str, Any] = {}
        if doctor_id:
            params["doctor_id"] = doctor_id
        if specialization:
            params["specialization"] = specialization
        if date:
            params["date"] = date
        if time_range:
            params["time_from"] = time_range.get("from", "")
            params["time_to"] = time_range.get("to", "")
        return await self.request("GET", "/api/v1/slots/available", params=params)

    async def book_appointment(
        self,
        patient_id: str,
        slot_id: str,
        appointment_type: str = "consultation",
        reason: str = "",
    ) -> dict:
        """Book an appointment slot."""
        return await self.request(
            "POST",
            "/api/v1/appointments",
            data={
                "patient_id": patient_id,
                "slot_id": slot_id,
                "type": appointment_type,
                "reason": reason,
            },
        )

    async def cancel_appointment(
        self,
        appointment_id: str,
        reason: str = "",
    ) -> dict:
        """Cancel an existing appointment."""
        return await self.request(
            "POST",
            f"/api/v1/appointments/{appointment_id}/cancel",
            data={"reason": reason},
        )

    async def reschedule_appointment(
        self,
        appointment_id: str,
        new_slot_id: str,
    ) -> dict:
        """Reschedule an appointment to a new slot."""
        return await self.request(
            "POST",
            f"/api/v1/appointments/{appointment_id}/reschedule",
            data={"new_slot_id": new_slot_id},
        )


class PatientMemoryClient(DownstreamClient):
    """HTTP client for the Patient Memory service."""

    def __init__(self) -> None:
        config = get_config()
        super().__init__(
            base_url=config.patient_memory_url,
            service_name="patient-memory",
        )

    async def lookup_patient(
        self,
        phone: str = "",
        name: str = "",
        mrn: str = "",
    ) -> dict:
        """Look up a patient by phone, name, or MRN."""
        params: dict[str, str] = {}
        if phone:
            params["phone"] = phone
        if name:
            params["name"] = name
        if mrn:
            params["mrn"] = mrn
        return await self.request("GET", "/api/v1/patients/search", params=params)
