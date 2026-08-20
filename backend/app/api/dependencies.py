from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.services.cv_ingestion import CVIngestionService
from app.services.pdf import PdfInspector, PdfOcrExtractor, NativePdfTextExtractor
from app.services.storage import LocalStorageService, StorageService


@lru_cache
def get_storage_service() -> StorageService:
    return LocalStorageService(get_settings())

@lru_cache
def get_pdf_inspector() -> PdfInspector:
    return PdfInspector(get_settings())

@lru_cache
def get_native_pdf_text_extractor() -> NativePdfTextExtractor:
    return NativePdfTextExtractor(get_settings())

@lru_cache
def get_pdf_ocr_extractor() -> PdfOcrExtractor:
    return PdfOcrExtractor(get_settings())

def get_cv_ingestion_service(
    storage_service: StorageService = Depends(get_storage_service),
    pdf_inspector: PdfInspector = Depends(get_pdf_inspector),
    text_extractor: NativePdfTextExtractor = Depends(get_native_pdf_text_extractor),
    ocr_extractor: PdfOcrExtractor = Depends(get_pdf_ocr_extractor),
) -> CVIngestionService:
    return CVIngestionService(
        storage=storage_service,
        pdf_inspector=pdf_inspector,
        text_extractor=text_extractor,
        ocr_extractor=ocr_extractor,
    )


CVIngestionServiceDependency = Annotated[
    CVIngestionService,
    Depends(get_cv_ingestion_service),
]