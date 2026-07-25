from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.response import ApiResponse
from app.utils.responses import success_response

router = APIRouter(tags=["System"])


@router.get("/health")
async def health_check(settings: SettingsDep) -> ApiResponse[dict[str, str]]:
    return success_response(
        message="Service is healthy.",
        data={
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )