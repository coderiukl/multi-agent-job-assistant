from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies import CVIngestionServiceDependency
from app.schemas.cv import CVUploadData, PdfInspectionData, PdfMetadataData
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
    ingestion_service: CVIngestionServiceDependency,
) -> ApiResponse[CVUploadData]:

    result = await ingestion_service.ingest(file)

    stored_file = result.stored_file
    inspection = result.inspection
    metadata = inspection.metadata

    return ApiResponse(
        message="CV uploaded and inspected successfully.",
        data=CVUploadData(
            file_id=stored_file.file_id,
            original_filename=stored_file.original_filename,
            content_type=stored_file.content_type,
            size_bytes=stored_file.size_bytes,
            inspection=PdfInspectionData(
                page_count=inspection.page_count,
                is_repaired=inspection.is_repaired,
                metadata=PdfMetadataData(
                    title=metadata.title,
                    author=metadata.author,
                    subject=metadata.subject,
                    keywords=metadata.keywords,
                    creator=metadata.creator,
                    producer=metadata.producer,
                    creation_date=metadata.creation_date,
                    modification_date=metadata.modification_date
                ),
            ),
        ),
    )