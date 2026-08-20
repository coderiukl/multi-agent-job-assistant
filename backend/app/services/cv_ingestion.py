import logging
from dataclasses import dataclass

from fastapi import UploadFile

from app.services.pdf.inspector import PdfInspector
from app.services.pdf.models import NativeTextExtractionResult, PdfInspectionResult
from app.services.pdf.text_extractor import NativePdfTextExtractor

from app.services.storage import StorageService, StoredFile

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class CVIngestionResult:
    stored_file: StoredFile
    inspection: PdfInspectionResult
    extraction: NativeTextExtractionResult


class CVIngestionService:
    def __init__(self, *, storage: StorageService, pdf_inspector: PdfInspector, text_extractor: NativePdfTextExtractor) -> None:
        self._storage = storage
        self._pdf_inspector = pdf_inspector
        self._text_extractor = text_extractor

    async def ingest(self, upload_file: UploadFile) -> CVIngestionResult:
        stored_file = await self._storage.save(upload_file)

        try:
            inspection = await self._pdf_inspector.inspect(stored_file.path)
            extraction = await self._text_extractor.extract(stored_file.path)

        except Exception:
            await self._storage.delete(stored_file)
            raise

        return CVIngestionResult(stored_file=stored_file, inspection=inspection, extraction=extraction)
