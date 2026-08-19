from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthData
from app.schemas.response import ApiResponse

router = APIRouter(tags=["System"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get(
    "/health",
    response_model=ApiResponse[HealthData],
    summary="Check service health",
)
async def health_check(settings: SettingsDependency) -> ApiResponse[HealthData]:
    return ApiResponse(
        message="Service is healthy.",
        data=HealthData(
            status="healthy",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        ),
    )
