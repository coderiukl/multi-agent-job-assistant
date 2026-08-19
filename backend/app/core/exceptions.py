from typing import Any


class AppException(Exception):
    """Base exception for expected application errors."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ResourceNotFoundException(AppException):
    def __init__(self, *, resource: str, identifier: str | int) -> None:
        super().__init__(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} was not found.",
            details={
                "resource": resource,
                "identifier": str(identifier),
            },
        )


class FileValidationException(AppException):
    def __init__(
        self,
        *,
        message: str = "The uploaded file is invalid.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=422,
            code="FILE_VALIDATION_ERROR",
            message=message,
            details=details,
        )


class ExternalServiceException(AppException):
    def __init__(
        self,
        *,
        service: str,
        message: str = "An external service is unavailable.",
    ) -> None:
        super().__init__(
            status_code=502,
            code="EXTERNAL_SERVICE_ERROR",
            message=message,
            details={"service": service},
        )
