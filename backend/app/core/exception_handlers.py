import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import AppException
from app.schemas.error import ErrorPayload, ErrorResponse

logger = logging.getLogger("app.exceptions")


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _build_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _get_request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id

    response = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=message,
            details=jsonable_encoder(details),
        ),
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
        headers=response_headers,
    )


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    log_level = logging.ERROR if exc.status_code >= 500 else logging.WARNING

    logger.log(
        log_level,
        "Application exception: %s",
        exc.code,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
            "error_code": exc.code,
            "request_id": _get_request_id(request),
        },
    )

    return _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning(
        "Request validation failed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": 422,
            "error_code": "REQUEST_VALIDATION_ERROR",
            "request_id": _get_request_id(request),
        },
    )

    return _build_error_response(
        request=request,
        status_code=422,
        code="REQUEST_VALIDATION_ERROR",
        message="The request data is invalid.",
        details={"errors": exc.errors()},
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    message = (
        exc.detail
        if isinstance(exc.detail, str)
        else "The request could not be completed."
    )
    details = None if isinstance(exc.detail, str) else exc.detail

    logger.warning(
        "HTTP exception: %s",
        exc.status_code,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
            "error_code": f"HTTP_{exc.status_code}",
            "request_id": _get_request_id(request),
        },
    )

    return _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=message,
        details=details,
        headers=exc.headers,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled application exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "error_code": "INTERNAL_SERVER_ERROR",
            "request_id": _get_request_id(request),
        },
    )

    return _build_error_response(
        request=request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        AppException,
        app_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        HTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
