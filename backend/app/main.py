import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.middleware.request_context import RequestContextMiddleware

from app.schemas.health import HealthData
from app.schemas.response import ApiResponse

settings = get_settings()
configure_logging(settings)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.settings = settings

    logger.info(
        "Application started: %s version=%s environment=%s",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    try:
        yield
    finally:
        logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

@app.get(
    "/health",
    response_model=ApiResponse[HealthData],
    tags=["System"],
)
async def health_check() -> ApiResponse[HealthData]:
    health_data = HealthData(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    return ApiResponse(
        message="Service is healthy.",
        data=health_data,
    )
