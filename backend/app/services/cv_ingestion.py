import logging
from dataclasses import dataclass

from fastapi import UploadFile

from app.services.pdf import PdfInspectionResult, PdfInspector
from app.services.storage import StorageService, StoredFile

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class CVIngestionResult:
    stored_file: StoredFile
    inspection: PdfInspectionResult

class CVIngestionService:
    def __init__(self, *, storage_service: StorageService, pdf_inspector: PdfInspector) -> None:
        self._storage_service = storage_service
        self._pdf_inspector = pdf_inspector

    async def ingest(self, file: UploadFile) -> CVIngestionResult:
        stored_file = await self._storage_service.save_cv(file)

        try:
            inspection = await self._pdf_inspector.inspect(stored_file.path)

        except Exception:
            try:
                await self._storage_service.delete(stored_file)
            except Exception:
                logger.exception(
                    "Failed to rollback invalid CV upload",
                    extra={
                        "file_id": stored_file.file_id,
                    },
                )

            raise

        return CVIngestionResult(stored_file=stored_file, inspection=inspection)