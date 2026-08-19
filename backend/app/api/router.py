from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings

def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    router.include_router(health_router)
    router.include_router(v1_router, prefix=settings.api_prefix)

    return router
