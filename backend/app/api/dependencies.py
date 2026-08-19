from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.services.cv_ingestion import CVIngestionService
from app.services.pdf import PdfInspector
from app.services.storage import LocalStorageService, StorageService


@lru_cache
def get_storage_service() -> StorageService:
    return LocalStorageService(get_settings())

@lru_cache
def get_pdf_inspector() -> PdfInspector:
    return PdfInspector(get_settings())

@lru_cache
def get_cv_ingestion_service() -> CVIngestionService:
    return CVIngestionService(
        storage_service=get_storage_service(),
        pdf_inspector=get_pdf_inspector(),
    )

CVIngestionServiceDependency = Annotated[
    CVIngestionService,
    Depends(get_cv_ingestion_service),
]