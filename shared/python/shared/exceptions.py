"""Custom exception hierarchy for all services."""


class BaseServiceError(Exception):
    """Base exception for all service errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationError(BaseServiceError):
    """Input validation failed."""

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)


class NotFoundError(BaseServiceError):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str):
        self.resource = resource
        self.identifier = identifier
        super().__init__(
            f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            status_code=404,
        )


class ConflictError(BaseServiceError):
    """Resource conflict (e.g., double-booking)."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT", status_code=409)


class ServiceUnavailableError(BaseServiceError):
    """Downstream service is unavailable."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(
            f"Service unavailable: {service_name}",
            code="SERVICE_UNAVAILABLE",
            status_code=503,
        )


class CircuitOpenError(BaseServiceError):
    """Circuit breaker is open for the target service."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(
            f"Circuit breaker open for: {service_name}",
            code="CIRCUIT_OPEN",
            status_code=503,
        )


class AuthenticationError(BaseServiceError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="UNAUTHORIZED", status_code=401)


class AuthorizationError(BaseServiceError):
    """Authorization failed - insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, code="FORBIDDEN", status_code=403)


class RateLimitError(BaseServiceError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s",
            code="RATE_LIMITED",
            status_code=429,
        )
