import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.core.exceptions import AppException
from app.schemas.error import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

def _create_error_response(*, code: str, message: str, details: list[ErrorDetail] | dict[str, Any] | None = None) -> dict[str, Any]:
    response = ErrorResponse(
        code=code,
        message=message,
        details=details,
    )

    return response.model_dump(exclude_none=True)

async def app_exception_handler(request: Request, exception: AppException) -> JSONResponse:
    """Xử lý các exception nghiệp vụ của ứng dụng."""

    logger.warning(
        "Application exception",
        extra={
            "error_code": exception.code,
            "status_code": exception.status_code,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=exception.status_code,
        content=_create_error_response(
            code=exception.code,
            message=exception.message,
            details=exception.details,
        ),
    )

async def http_exception_handler(request: Request, exception: HTTPException) -> JSONResponse:
    """Chuẩn hóa HTTPException của FastAPI."""
    logger.warning(
        "HTTP exception",
        extra={
            "status_code": exception.status_code,
            "path": request.url.path,
            "method": request.method,
        },
    )

    message = "Request không hợp lệ."
    details: dict[str, Any] | None = None

    if isinstance(exception.detail, str):
        message = exception.detail
    elif exception.detail is not None:
        details = {
            "detail": exception.detail,
        }

    return JSONResponse(
        status_code=exception.status_code,
        content=_create_error_response(
            code=f"HTTP_{exception.status_code}",
            message=message,
            details=details,
        ),
        headers=exception.headers,
    )

async def validation_exception_handler(request: Request, exception: RequestValidationError) -> JSONResponse:
    """Xử lý lỗi validation request từ Pydantic/FastAPI."""

    error_details: list[ErrorDetail] = []

    for error in exception.errors():
        location = error.get("loc", ())
        field_parts = [
            str(part)
            for part in location
            if part not in {"body", "query", "path", "header"}
        ]

        field = ".".join(field_parts) if field_parts else None

        error_details.append(
            ErrorDetail(
                field=field,
                message=error.get("msg", "Dữ liệu không hợp lệ."),
                type=error.get("type"),
            )
        )

    logger.warning(
        "Request validation failed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "validation_errors": len(error_details),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_create_error_response(
            code="VALIDATION_ERROR",
            message="Dữ liệu request không hợp lệ.",
            details=error_details,
        ),
    )


async def unhandled_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    """Bắt các exception chưa được xử lý.

    Không trả nội dung exception cho client để tránh lộ thông tin hệ thống.
    """

    logger.exception(
        "Unhandled application exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exception).__name__,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_create_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Hệ thống đã xảy ra lỗi. Vui lòng thử lại sau.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Đăng ký toàn bộ exception handler cho FastAPI application."""

    app.add_exception_handler(
        AppException,
        app_exception_handler,
    )
    app.add_exception_handler(
        HTTPException,
        http_exception_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )