from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies import CVIngestionServiceDependency, CVProcessingServiceDependency
from app.schemas.cv import CVUploadData, PdfInspectionData, PdfMetadataData, NativeTextExtractionData, OcrExtractionData
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
    processing_service: CVProcessingServiceDependency,
) -> ApiResponse[CVUploadData]:

    processing_result = await processing_service.process(file)

    result = processing_result.ingestion
    profile = processing_result.profile

    stored_file = result.stored_file
    inspection = result.inspection
    metadata = inspection.metadata
    extraction = result.extraction
    ocr_extraction = result.ocr_extraction

    return ApiResponse(
        message="CV uploaded and parsed successfully.",
        data=CVUploadData(
            file_id=stored_file.file_id,
            file_name=stored_file.original_filename,
            file_size=stored_file.size_bytes,
            content_type=stored_file.content_type,
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
            extraction=NativeTextExtractionData(
                total_character_count=extraction.total_character_count,
                total_word_count=extraction.total_word_count,
                native_page_count=extraction.native_page_count,
                ocr_required_page_numbers=list(extraction.ocr_required_page_numbers),
            ),
            ocr=OcrExtractionData(
                ocr_page_count=ocr_extraction.ocr_page_count,
                total_character_count=ocr_extraction.total_character_count,
                total_word_count=ocr_extraction.total_word_count,
                average_confidence=sum(
                    page.average_confidence
                    for page in ocr_extraction.pages
                ) / len(ocr_extraction.pages)
                if result.ocr_extraction.pages else 0.0
            ),
            profile=profile,
        ),
    )
