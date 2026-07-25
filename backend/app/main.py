import logging

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging

from app.schemas.response import ApiResponse
from app.utils.responses import success_response

settings = get_settings()
configure_logging(settings)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Application starting | name=%s | environment=%s",
        settings.app_name,
        settings.environment,
    )

    yield

    logger.info("Application shutting down")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

register_exception_handlers(app)

@app.get("/health", tags=["System"])
async def health_check() -> ApiResponse[dict[str, str]]:
    return success_response(
        message="Service is healthy.",
        data={
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )
