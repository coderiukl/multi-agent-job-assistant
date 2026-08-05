from typing import Any


class AppException(Exception):
    """Base exception for application business errors."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ResourceNotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, *, resource: str, resource_id: str | int | None = None) -> None:
        details: dict[str, Any] = {
            "resource": resource,
        }

        if resource_id is not None:
            details["resource_id"] = resource_id

        super().__init__(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} khong ton tai.",
            details=details,
        )


class FileValidationException(AppException):
    """Raised when an uploaded file is invalid."""

    def __init__(self, *, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=400,
            code="INVALID_FILE",
            message=message,
            details=details,
        )


class PDFInspectionException(AppException):
    """Raised when PDF inspection or extraction fails."""

    def __init__(self, *, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            status_code=400,
            code="PDF_INSPECTION_FAILED",
            message=message,
            details=details,
        )


class ExternalServiceException(AppException):
    """Raised when an external service fails."""

    def __init__(self, *, service: str, message: str | None = None) -> None:
        super().__init__(
            status_code=503,
            code="EXTERNAL_SERVICE_ERROR",
            message=message or f"Service {service} is currently unavailable.",
            details={"service": service},
        )
