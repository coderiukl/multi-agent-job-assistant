import logging

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging

from app.api.v1.router import router as health_router

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

app.include_router(health_router, prefix=settings.api_v1_prefix)
