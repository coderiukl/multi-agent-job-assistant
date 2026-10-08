from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile, status

from app.api.resource_dependencies import (
    AuthorizedCVProcessingServiceDependency,
    AuthorizedCVTaskServiceDependency,
)
from app.schemas.cv_profile import CVProfile
from app.schemas.cv_task import CVTaskAcceptedData, CVTaskStatusData
from app.schemas.error import ErrorResponse
from app.schemas.response import ApiResponse

router = APIRouter()


@router.get(
    "/{cv_id}",
    response_model=ApiResponse[CVProfile],
    summary="Get an owned parsed CV profile",
)
async def get_cv(
    cv_id: str,
    processing_service: AuthorizedCVProcessingServiceDependency,
) -> ApiResponse[CVProfile]:
    profile = await processing_service.get_profile(cv_id)
    return ApiResponse(
        message="CV profile retrieved successfully.",
        data=profile,
    )


@router.patch(
    "/{cv_id}",
    response_model=ApiResponse[CVProfile],
    summary="Replace an owned parsed CV profile after user review",
)
async def update_cv(
    cv_id: str,
    profile: CVProfile,
    processing_service: AuthorizedCVProcessingServiceDependency,
) -> ApiResponse[CVProfile]:
    updated_profile = await processing_service.update_profile(
        cv_id=cv_id,
        profile=profile,
    )
    return ApiResponse(
        message="CV profile updated successfully.",
        data=updated_profile,
    )


@router.delete(
    "/{cv_id}",
    response_model=ApiResponse[dict[str, bool]],
    summary="Delete an owned CV and its parsed profile",
)
async def delete_cv(
    cv_id: str,
    processing_service: AuthorizedCVProcessingServiceDependency,
) -> ApiResponse[dict[str, bool]]:
    await processing_service.delete(cv_id)
    return ApiResponse(
        message="CV deleted successfully.",
        data={"deleted": True},
    )


@router.post(
    "",
    response_model=ApiResponse[CVTaskAcceptedData],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CV and enqueue durable processing",
    responses={
        413: {
            "model": ErrorResponse,
            "description": "File exceeds the size limit.",
        },
        415: {
            "model": ErrorResponse,
            "description": "Unsupported file type.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Invalid PDF file.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Storage operation failed.",
        },
        502: {
            "model": ErrorResponse,
            "description": "LLM provider or structured output failed.",
        },
    },
)
async def upload_cv(
    file: Annotated[
        UploadFile,
        File(description="PDF CV file."),
    ],
    task_service: AuthorizedCVTaskServiceDependency,
) -> ApiResponse[CVTaskAcceptedData]:
    task = await task_service.enqueue(file)
    return ApiResponse(
        message="CV uploaded and queued for processing.",
        data=CVTaskAcceptedData(
            task_id=task.task_id,
            cv_id=task.cv_id,
            file_name=task.original_filename,
            file_size=task.size_bytes,
            content_type=task.content_type,
            status=task.status,
        ),
    )


@router.get(
    "/processing-tasks/{task_id}",
    response_model=ApiResponse[CVTaskStatusData],
    summary="Get an owned CV processing task",
)
async def get_cv_processing_task(
    task_id: UUID,
    task_service: AuthorizedCVTaskServiceDependency,
) -> ApiResponse[CVTaskStatusData]:
    task = await task_service.get(task_id)
    return ApiResponse(
        message="CV processing task retrieved successfully.",
        data=task,
    )
