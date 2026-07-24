from typing import Any


class AppException(Exception):
    """Base exception cho các lỗi nghiệp vụ trong ứng dụng."""

    def __init__(self, *, status_code: int, code: str, message: str, details: dict[str, Any] | list[Any] | None = None) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

class ResourceNotFoundException(AppException):
    """Exception được sử dụng khi tài nguyên không tồn tại."""

    def __init__(self, *, resource: str, resource_id: str | int | None = None) -> None:
        details: dict[str, Any] = {
            "resource": resource,
        }

        if resource_id is not None:
            details["resource_id"] = resource_id

        super().__init__(
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} không tồn tại.",
            details=details,
        )

class FileValidationException(AppException):
    """Exception dành cho file upload không hợp lệ."""

    def __init__(self, *, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(status_code=400, code="INVALID_FILE", message=message, details=details)

class ExternalServiceException(AppException):
    """Exception khi dịch vụ bên ngoài gặp lỗi."""

    def __init__(self, *, service: str, message: str | None = None) -> None:
        super().__init__(status_code=503, code="EXTERNAL_SERVICE_ERROR", message=message or f"Dịch vụ {service} hiện không khả dụng.", details={"service": service})
        