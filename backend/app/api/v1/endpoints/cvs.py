from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies import StorageServiceDependency
from app.schemas.cv import CVUploadData
from app.schemas.error import ErrorResponse
from app.schemas.response import ApiResponse

router = APIRouter()

@router.post(
    "",
    response_model=ApiResponse[CVUploadData],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CV",
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
    },
)

async def upload_cv(
    file: Annotated[
        UploadFile,
        File(description="PDF CV file."),
    ],
    storage_service: StorageServiceDependency,
) -> ApiResponse[CVUploadData]:

    stored_file = await storage_service.save_cv(file)

    return ApiResponse(
        message="CV uploaded successfully.",
        data=CVUploadData(
            file_id=stored_file.file_id,
            original_filename=stored_file.original_filename,
            content_type=stored_file.content_type,
            size_bytes=stored_file.size_bytes,
        ),
    )